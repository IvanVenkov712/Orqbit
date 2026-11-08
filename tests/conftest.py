"""Real PostgreSQL, with a fresh migrated schema for each pytest run."""

import os
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema, DropSchema

from models.base import Base
from models.supported_types import SupportedJobType
from models.user import User
from models.worker import Worker

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def alembic_config():
    return Config(str(ROOT / "alembic.ini"))


@pytest.fixture(scope="session")
def database_engine(alembic_config):
    value = os.environ.get("TEST_DATABASE_URL")
    if not value:
        raise pytest.UsageError(
            "Set TEST_DATABASE_URL to a PostgreSQL database ending in '_test'."
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

    schema = f"test_{uuid4().hex}"
    admin_engine = create_engine(url, connect_args={"connect_timeout": 5})
    with admin_engine.begin() as connection:
        connection.execute(CreateSchema(schema))

    # Each run starts empty; API, migrations, and assertions use this same schema.
    isolated_url = url.update_query_dict(
        {"options": f"-csearch_path={schema} -ctimezone=UTC"}
    )
    engine = create_engine(isolated_url)
    try:
        with pytest.MonkeyPatch.context() as environment:
            environment.setenv(
                "DATABASE_URL", isolated_url.render_as_string(hide_password=False)
            )
            environment.setenv("LEASE_SECONDS", "120")
            environment.setenv("PROTRACTION_SECONDS", "60")
            environment.setenv("SECRET_KEY", "0" * 64)
            environment.setenv("ALGORITHM", "HS256")
            environment.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
            command.upgrade(alembic_config, "head")
            yield engine
    finally:
        # The API creates its own pool, pointing to the same temporary schema.
        if api_database := sys.modules.get("database"):
            api_database.engine.dispose()
            api_database.readiness_engine.dispose()
        engine.dispose()
        try:
            with admin_engine.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))
        finally:
            admin_engine.dispose()


@pytest.fixture
def database(database_engine):
    """Keep tests independent while allowing real request-level commits."""
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
    # Import only after the session fixture has selected the test configuration.
    from main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def user(database):
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
