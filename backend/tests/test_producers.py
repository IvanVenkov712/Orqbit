"""Producer service and DTO coverage while its schema migration is pending."""

from unittest.mock import Mock

import pytest
from psycopg.errors import ForeignKeyViolation, NotNullViolation, UniqueViolation
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dto.producer import ProducerAPIKeyResponse, ProducerCreate, ProducerCreateResponse
from models.producers import Producer
from models.user import User
from services.api_key_auth import hash_api_key
from services.producer import (
    ProducerCreationConflict,
    ProducerDeletionConflict,
    accessible_producers_query,
    create_producer,
    delete_producer,
    get_owned_producer,
    producer_accessible,
    producer_read_from_producer,
    reissue_producer_api_key,
)


@pytest.fixture
def producer():
    return Producer(
        id=10,
        name="test-producer",
        user=User(id=1, username="owner"),
        user_id=1,
        active=True,
        secret_api_key_hash=hash_api_key("old-key"),
    )


@pytest.mark.parametrize("name", ["", "ab", "x" * 17, "has spaces", "bad!"])
def test_producer_create_rejects_invalid_names(name):
    with pytest.raises(ValidationError):
        ProducerCreate(name=name)


def test_create_producer_hashes_key_and_returns_producer_fields(producer):
    session = Mock(spec=Session)

    def refresh(created):
        created.id = producer.id
        created.user_id = producer.user_id
        created.active = True

    session.refresh.side_effect = refresh
    response = create_producer(
        session, producer.user, ProducerCreate(name="new-producer")
    )

    created = session.add.call_args.args[0]
    assert isinstance(created, Producer)
    assert created.user is producer.user
    assert created.secret_api_key_hash == hash_api_key(response.secret_api_key)
    assert created.secret_api_key_hash != response.secret_api_key
    assert isinstance(response, ProducerCreateResponse)
    assert response.model_dump(exclude={"secret_api_key"}) == {
        "id": 10,
        "name": "new-producer",
        "active": True,
        "user_id": 1,
        "owner_username": "owner",
    }
    session.commit.assert_called_once()


@pytest.mark.parametrize("duplicate_name", [True, False])
def test_create_producer_rolls_back_and_only_translates_name_conflicts(
    producer, duplicate_name
):
    session = Mock(spec=Session)
    error = IntegrityError(None, None, UniqueViolation())
    session.commit.side_effect = error
    session.scalar.return_value = 20 if duplicate_name else None

    with pytest.raises(
        ProducerCreationConflict if duplicate_name else IntegrityError
    ) as raised:
        create_producer(session, producer.user, ProducerCreate(name=producer.name))

    session.rollback.assert_called_once()
    if not duplicate_name:
        assert raised.value is error


def test_owned_producer_lookup_filters_producer_and_owner_and_locks(producer):
    session = Mock(spec=Session)
    session.scalar.return_value = producer
    assert get_owned_producer(10, session, producer.user) is producer

    stmt = session.scalar.call_args.args[0]
    compiled = stmt.compile(dialect=postgresql.dialect())
    assert stmt.column_descriptions[0]["entity"] is Producer
    assert stmt.get_final_froms() == [Producer.__table__]
    assert "producers.id =" in str(compiled)
    assert "producers.user_id =" in str(compiled)
    assert set(compiled.params.values()) == {10, 1}
    assert "FOR UPDATE" in str(compiled)

    session.scalar.return_value = None
    assert get_owned_producer(999, session, producer.user) is None


def test_producer_visibility_is_owner_only(producer):
    other = User(id=2, username="other")
    assert producer_accessible(producer, producer.user)
    assert not producer_accessible(producer, other)

    stmt = accessible_producers_query(other)
    compiled = stmt.compile(dialect=postgresql.dialect())
    assert stmt.column_descriptions[0]["entity"] is Producer
    assert "WHERE producers.user_id =" in str(compiled)
    assert list(compiled.params.values()) == [other.id]


def test_producer_read_excludes_credentials(producer):
    data = producer_read_from_producer(producer).model_dump()
    assert data == {
        "id": 10,
        "name": "test-producer",
        "active": True,
        "user_id": 1,
        "owner_username": "owner",
    }


def test_reissue_producer_key_replaces_hash_and_only_returns_key(producer):
    session = Mock(spec=Session)
    old_hash = producer.secret_api_key_hash
    response = reissue_producer_api_key(session, producer)

    assert isinstance(response, ProducerAPIKeyResponse)
    assert producer.secret_api_key_hash == hash_api_key(response.secret_api_key)
    assert producer.secret_api_key_hash != old_hash
    assert response.model_dump() == {"secret_api_key": response.secret_api_key}
    session.commit.assert_called_once()


@pytest.mark.parametrize("has_jobs", [True, False])
def test_delete_producer_preserves_published_jobs(producer, has_jobs):
    session = Mock(spec=Session)
    session.scalar.side_effect = [producer.id, 42 if has_jobs else None]

    if has_jobs:
        with pytest.raises(ProducerDeletionConflict, match="referenced by jobs"):
            delete_producer(session, producer)
        session.delete.assert_not_called()
        session.commit.assert_not_called()
    else:
        delete_producer(session, producer)
        session.delete.assert_called_once_with(producer)
        session.commit.assert_called_once()


@pytest.mark.parametrize("foreign_key", [True, False])
def test_delete_producer_rolls_back_and_only_translates_foreign_key_errors(
    producer, foreign_key
):
    session = Mock(spec=Session)
    session.scalar.side_effect = [producer.id, None]
    error = IntegrityError(
        None, None, ForeignKeyViolation() if foreign_key else NotNullViolation()
    )
    session.commit.side_effect = error

    with pytest.raises(
        ProducerDeletionConflict if foreign_key else IntegrityError
    ) as raised:
        delete_producer(session, producer)

    session.rollback.assert_called_once()
    if not foreign_key:
        assert raised.value is error
