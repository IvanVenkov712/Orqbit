"""Real PostgreSQL, with a fresh migrated schema for each pytest run."""

import sys
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema, DropSchema

ROOT = Path(__file__).resolve().parents[1]
TEST_DATABASE = pytest.StashKey[tuple[URL, str]]()


class TestDatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env.test",
        env_prefix="TEST_",
        extra="ignore",
        hide_input_in_errors=True,
    )

    database_url: str | None = None


def _test_database_url() -> URL:
    value = TestDatabaseSettings().database_url
    if not value:
        raise pytest.UsageError(
            "Set TEST_DATABASE_URL in the environment or .env.test "
            "to a PostgreSQL database ending in '_test'."
        )
    try:
        url = make_url(value)
    except (ArgumentError, ValueError):
        # Do not include a potentially credential-bearing URL in the message.
        raise pytest.UsageError("Invalid TEST_DATABASE_URL") from None

    if url.drivername != "postgresql+psycopg" or not (
        url.database and url.database.endswith("_test")
    ):
        raise pytest.UsageError(
            "TEST_DATABASE_URL must use postgresql+psycopg and a database "
            "ending in '_test'."
        )
    return url


def pytest_configure(config):
    # Configure before collection: importing a model may also import settings.
    url = _test_database_url()
    if "config" in sys.modules or "database" in sys.modules:
        raise pytest.UsageError(
            "Application configuration was imported before test database isolation."
        )

    schema = f"test_{uuid4().hex}"
    isolated_url = url.update_query_dict(
        {"options": f"-csearch_path={schema} -ctimezone=UTC"}
    )
    config.stash[TEST_DATABASE] = (isolated_url, schema)
    environment = pytest.MonkeyPatch()
    config.add_cleanup(environment.undo)
    environment.setenv(
        "DATABASE_URL", isolated_url.render_as_string(hide_password=False)
    )
    environment.setenv("LEASE_SECONDS", "120")
    environment.setenv("LEASE_EXTENSION_SECONDS", "60")
    environment.setenv("RECOVERY_INTERVAL_SECONDS", "5")
    environment.setenv("RECOVERY_BATCH_SIZE", "1000")
    environment.setenv("MAX_UNKNOWN_DATABASE_ERRORS", "3")
    environment.setenv("SECRET_KEY", "0" * 64)
    environment.setenv("ALGORITHM", "HS256")
    environment.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30")


@pytest.fixture(scope="session")
def alembic_config():
    return Config(str(ROOT / "alembic.ini"))


@pytest.fixture(scope="session")
def database_engine(alembic_config, pytestconfig):
    import database as api_database
    from config import settings

    isolated_url, schema = pytestconfig.stash[TEST_DATABASE]
    # Fail before any connection or migration if cached configuration diverges.
    if make_url(str(settings.database_url)) != isolated_url or any(
        engine.url != isolated_url
        for engine in (
            api_database.engine,
            api_database.readiness_engine,
            api_database.SessionLocal.kw["bind"],
        )
    ):
        raise pytest.UsageError(
            "Application settings and engines must use the isolated test database URL."
        )

    engine = create_engine(isolated_url, connect_args={"connect_timeout": 5})
    created = False
    try:
        with engine.begin() as connection:
            connection.execute(CreateSchema(schema))
        created = True
        command.upgrade(alembic_config, "head")
        yield engine
    finally:
        api_database.engine.dispose()
        api_database.readiness_engine.dispose()
        try:
            if created:
                with engine.begin() as connection:
                    connection.execute(DropSchema(schema, cascade=True))
        finally:
            engine.dispose()


@pytest.fixture
def database(database_engine):
    """Keep tests independent while allowing real request-level commits."""
    from models.base import Base

    with database_engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())
    try:
        yield database_engine
    finally:
        with database_engine.begin() as connection:
            for table in reversed(Base.metadata.sorted_tables):
                connection.execute(table.delete())


@pytest.fixture
def client(database):
    from main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def user(database):
    from models.user import User

    with Session(database, expire_on_commit=False) as session:
        owner = User(
            username="job-test",
            email="job-test@example.com",
            full_name="Job test",
            hashed_password="unused",
        )
        session.add(owner)
        session.commit()
        return owner


@pytest.fixture
def user_headers(user):
    from services.user_auth import create_access_token

    return {"Authorization": f"Bearer {create_access_token(user.username)}"}


@pytest.fixture
def worker_factory(database, user):
    from models.supported_types import SupportedJobType
    from models.worker import Worker
    from services.worker_auth import hash_api_key

    def create_worker(supported_types=("example",)):
        api_key = f"oqb_{uuid4().hex}"
        with Session(database, expire_on_commit=False) as session:
            worker = Worker(
                name=f"worker-{uuid4().hex}",
                user_id=user.id,
                secret_api_key_hash=hash_api_key(api_key),
                supported_types=[
                    SupportedJobType(type_name=job_type) for job_type in supported_types
                ],
            )
            session.add(worker)
            session.commit()
            return worker, {"X-API-Key": api_key}

    return create_worker


@pytest.fixture
def claim_worker(worker_factory):
    return worker_factory()


@pytest.fixture
def claimed_attempt(client, database, claim_worker):
    from models.job import Job

    worker, headers = claim_worker
    with Session(database) as session:
        session.add(
            Job(
                job_type="example",
                params={"input": True},
                user_id=worker.user_id,
                idempotency_key="lease-test",
                request_fingerprint="test-fingerprint",
            )
        )
        session.commit()
    response = client.post("/workers/claim", headers=headers)
    assert response.status_code == 200
    return response.json(), headers
