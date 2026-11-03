from typing import Annotated

from fastapi import Depends
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from config import settings

engine = create_engine(str(settings.database_url))

SessionLocal = sessionmaker(
    bind=engine,
    expire_on_commit=False,
)

def get_session():
    with SessionLocal() as session:
        yield session

SessionDep = Annotated[Session, Depends(get_session)]

