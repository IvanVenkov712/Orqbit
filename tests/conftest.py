"""Real PostgreSQL, with a fresh migrated schema for each pytest run."""

import os
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.schema import CreateSchema, DropSchema

from models.job import Job

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
            command.upgrade(alembic_config, "head")
            yield engine
    finally:
        # The API creates its own pool, pointing to the same temporary schema.
        if api_database := sys.modules.get("database"):
            api_database.engine.dispose()
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
        connection.execute(delete(Job))
    try:
        yield database_engine
    finally:
        with database_engine.begin() as connection:
            connection.execute(delete(Job))


@pytest.fixture
def client(database):
    # Import only after the session fixture has selected the test configuration.
    from main import app

    with TestClient(app) as test_client:
        yield test_client
