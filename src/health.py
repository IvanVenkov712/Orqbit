"""Read-only checks of the database required by this application version."""

from pathlib import Path

from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from database import readiness_engine
from models import Job

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
REQUIRED_HEADS = set(ScriptDirectory(str(MIGRATIONS)).get_heads())


def database_is_ready() -> bool:
    try:
        with readiness_engine.connect() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            connection.execute(text("SET LOCAL statement_timeout = '2s'"))
            current_heads = set(
                MigrationContext.configure(connection).get_current_heads()
            )
            if not REQUIRED_HEADS or current_heads != REQUIRED_HEADS:
                return False

            # A version stamp alone cannot prove that the actual tables exist.
            # LIMIT 0 checks every mapped column without reading queued jobs.
            connection.execute(select(Job.__table__).limit(0))
        return True
    except SQLAlchemyError:
        # Never put connection strings, credentials, or SQL in HTTP responses.
        return False
