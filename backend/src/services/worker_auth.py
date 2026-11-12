from typing import Annotated

from fastapi import Depends, HTTPException, Security
from sqlalchemy import select
from starlette import status

from database import SessionDep
from models.worker import Worker
from services.api_key_auth import api_key_scheme, hash_api_key


def get_current_worker(
    api_key: Annotated[str, Security(api_key_scheme)],
    session: SessionDep,
) -> Worker:

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "APIKey"},
    )

    if api_key is None:
        raise credentials_exception

    key_hash = hash_api_key(api_key)
    
    stmt = select(Worker).where(
        Worker.secret_api_key_hash == key_hash
    )
    worker = session.scalar(stmt)
    
    if worker is None or not worker.active:
        raise credentials_exception

    return worker

CurrentWorker = Annotated[Worker, Depends(get_current_worker)]