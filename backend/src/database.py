from typing import Annotated

from fastapi import Depends
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from config import settings

engine = create_engine(
    str(settings.database_url),
    pool_pre_ping=True,
    connect_args={"connect_timeout": 3},
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

