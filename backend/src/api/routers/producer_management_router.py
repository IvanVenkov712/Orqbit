from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, Response
from sqlalchemy.orm import joinedload

from database import SessionDep
from dto.producer import (
    ProducerAPIKeyResponse,
    ProducerCreate,
    ProducerCreateResponse,
    ProducerRead,
)
from models.producers import Producer
from models.user import User
from services.producer import (
    ProducerCreationConflict,
    ProducerDeletionConflict,
    accessible_producers_query,
    deactivate_producer,
    get_owned_producer,
    producer_read_from_producer,
    reissue_producer_api_key,
)
from services.producer import create_producer as create_producer_service
from services.producer import delete_producer as delete_producer_service
from services.user_auth import CurrentUser

producer_management_router = APIRouter()


@producer_management_router.post("/producers", response_model=ProducerCreateResponse)
def create_producer(payload: ProducerCreate, user: CurrentUser, session: SessionDep):
    try:
        return create_producer_service(session, user, payload)
    except ProducerCreationConflict as exc:
        raise HTTPException(409, str(exc)) from None


@producer_management_router.get("/producers", response_model=list[ProducerRead])
def list_producers(
    user: CurrentUser,
    session: SessionDep,
    query: str | None = Query(None, min_length=1, max_length=16),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    stmt = accessible_producers_query(user)
    if query is not None:
        stmt = stmt.where(Producer.name.icontains(query, autoescape=True))
    stmt = (
        stmt.options(joinedload(Producer.user).load_only(User.username))
        .order_by(Producer.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return [producer_read_from_producer(p) for p in session.scalars(stmt).all()]


@producer_management_router.get(
    "/producers/by-name/{name}", response_model=ProducerRead
)
def get_producer_by_name(
    name: Annotated[str, Path(pattern=r"^[a-zA-Z0-9_-]{3,16}$")],
    session: SessionDep,
    user: CurrentUser,
):
    stmt = (
        accessible_producers_query(user)
        .where(Producer.name == name)
        .options(joinedload(Producer.user).load_only(User.username))
    )
    producer = session.scalar(stmt)
    if producer is None:
        raise HTTPException(404, "Producer not found")
    return producer_read_from_producer(producer)


@producer_management_router.get("/producers/{producer_id}", response_model=ProducerRead)
def get_producer_by_id(producer_id: int, session: SessionDep, user: CurrentUser):
    stmt = (
        accessible_producers_query(user)
        .where(Producer.id == producer_id)
        .options(joinedload(Producer.user).load_only(User.username))
    )
    producer = session.scalar(stmt)
    if producer is None:
        raise HTTPException(404, "Producer not found")
    return producer_read_from_producer(producer)


@producer_management_router.post(
    "/producers/{producer_id}/api-key", response_model=ProducerAPIKeyResponse
)
def reissue_api_key(producer_id: int, session: SessionDep, user: CurrentUser):
    producer = get_owned_producer(producer_id, session, user)
    if producer is None:
        raise HTTPException(404, "Producer not found")
    return reissue_producer_api_key(session, producer)


@producer_management_router.delete("/producers/{producer_id}", status_code=204)
def delete_producer(producer_id: int, session: SessionDep, user: CurrentUser):
    producer = get_owned_producer(producer_id, session, user)
    if producer is None:
        raise HTTPException(404, "Producer not found")
    try:
        delete_producer_service(session, producer)
    except ProducerDeletionConflict as exc:
        raise HTTPException(409, str(exc)) from None
    return Response(status_code=204)


@producer_management_router.post(
    "/producers/{producer_id}/deactivate", response_model=ProducerRead
)
def deactivate(producer_id: int, session: SessionDep, user: CurrentUser):
    producer = get_owned_producer(producer_id, session, user)
    if producer is None:
        raise HTTPException(404, "Producer not found")
    return deactivate_producer(session, producer)
