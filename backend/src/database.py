from typing import Annotated

from fastapi import Depends
from sqlalchemy import create_engine, event
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from config import settings

engine = create_engine(
    str(settings.database_url),
    pool_pre_ping=True,
    pool_timeout=3,
    connect_args={"connect_timeout": 3},
)


@event.listens_for(engine, "connect")
def set_database_timeouts(dbapi_connection, connection_record):
    # Set session defaults outside a transaction so rollback cannot undo them.
    # Keep URL options (including the test schema's search_path) untouched.
    autocommit = dbapi_connection.autocommit
    dbapi_connection.autocommit = True
    try:
        with dbapi_connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('statement_timeout', %s, false), "
                "set_config('lock_timeout', %s, false)",
                (
                    f"{settings.database_statement_timeout_ms}ms",
                    f"{settings.database_lock_timeout_ms}ms",
                ),
            )
    finally:
        dbapi_connection.autocommit = autocommit


def is_transient_database_error(error: DBAPIError) -> bool:
    sqlstate = getattr(error.orig, "sqlstate", None)
    return (
        error.connection_invalidated
        # libpq connection failures can lack SQLSTATE.
        or (sqlstate is None and isinstance(error, OperationalError))
        or (
            sqlstate is not None
            and (
                sqlstate.startswith(("08", "40", "53"))
                or sqlstate in {"55P03", "57014", "57P01", "57P02", "57P03"}
            )
        )
    )


# Health probes use fresh connections and cannot wait behind the API's pool.
readiness_engine = create_engine(
    str(settings.database_url),
    poolclass=NullPool,
    connect_args={"connect_timeout": 3},
)

SessionLocal = sessionmaker(
    bind=engine,
    expire_on_commit=False,
)

def get_session():
    with SessionLocal() as session:
        yield session

SessionDep = Annotated[Session, Depends(get_session)]

