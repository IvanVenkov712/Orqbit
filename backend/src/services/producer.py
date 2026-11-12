from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dto.producer import (
    ProducerAPIKeyResponse,
    ProducerCreate,
    ProducerCreateResponse,
    ProducerRead,
)
from models.job import Job
from models.producers import Producer
from models.user import User
from services.api_key_auth import generate_api_key, hash_api_key


class ProducerCreationConflict(Exception):
    pass


class ProducerDeletionConflict(Exception):
    pass


def get_owned_producer(
    producer_id: int, session: Session, user: User
) -> Producer | None:
    return session.scalar(
        select(Producer)
        .where(Producer.id == producer_id, Producer.user_id == user.id)
        .with_for_update()
    )


def reissue_producer_api_key(
    session: Session, producer: Producer
) -> ProducerAPIKeyResponse:
    api_key = generate_api_key()
    producer.secret_api_key_hash = hash_api_key(api_key)
    session.commit()
    return ProducerAPIKeyResponse(secret_api_key=api_key)


def deactivate_producer(session: Session, producer: Producer) -> ProducerRead:
    producer.active = False
    session.commit()
    return producer_read_from_producer(producer)


def delete_producer(session: Session, producer: Producer) -> None:
    # Block new job foreign-key references until deletion commits or rolls back.
    session.scalar(
        select(Producer.id).where(Producer.id == producer.id).with_for_update()
    )
    job_id = session.scalar(
        select(Job.id).where(Job.producer_id == producer.id).limit(1)
    )
    if job_id is not None:
        raise ProducerDeletionConflict("Producer is referenced by jobs")

    session.delete(producer)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        if getattr(exc.orig, "sqlstate", None) != "23503":
            raise
        raise ProducerDeletionConflict("Producer is referenced by jobs") from None


def accessible_producers_query(user: User):
    return select(Producer).where(Producer.user_id == user.id)


def producer_accessible(producer: Producer, user: User) -> bool:
    return producer.user_id == user.id


def producer_read_from_producer(producer: Producer) -> ProducerRead:
    return ProducerRead(
        id=producer.id,
        name=producer.name,
        active=producer.active,
        user_id=producer.user_id,
        owner_username=producer.user.username,
    )


def create_producer(
    session: Session, user: User, payload: ProducerCreate
) -> ProducerCreateResponse:
    api_key = generate_api_key()
    producer = Producer(
        name=payload.name,
        user=user,
        secret_api_key_hash=hash_api_key(api_key),
    )

    session.add(producer)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing_id = session.scalar(
            select(Producer.id).where(Producer.name == payload.name)
        )
        if existing_id is not None:
            raise ProducerCreationConflict("Producer name already exists") from None
        raise
    session.refresh(producer)

    return ProducerCreateResponse(
        **producer_read_from_producer(producer).model_dump(),
        secret_api_key=api_key,
    )
