from datetime import datetime, timedelta, timezone
import uuid

import pytest
from fastapi import HTTPException, Response
from pydantic import ValidationError

from app.models import User, UserRole
from app.routers.users import export_users, import_users
from app.schemas import UserArchive, UserArchiveRecord

VALID_HASH = "$2b$12$" + ("a" * 53)


class FakeScalarResult:
    def __init__(self, rows: list[User]) -> None:
        self.rows = rows

    def all(self) -> list[User]:
        return self.rows


class FakeDb:
    def __init__(self, users: list[User]) -> None:
        self.users = users
        self.added: list[object] = []
        self.commits = 0
        self.rollbacks = 0
        self.flushes = 0

    async def scalars(self, statement: object) -> FakeScalarResult:
        return FakeScalarResult(list(self.users))

    def add(self, value: object) -> None:
        self.added.append(value)
        if isinstance(value, User) and value not in self.users:
            self.users.append(value)

    async def flush(self) -> None:
        self.flushes += 1

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


def make_user(**overrides: object) -> User:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    data = {
        "id": uuid.uuid4(),
        "email": "user@example.com",
        "password_hash": VALID_HASH,
        "role": UserRole.USER,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }
    data.update(overrides)
    return User(**data)


def archive_record(user: User, **overrides: object) -> UserArchiveRecord:
    data = {
        "id": user.id,
        "email": user.email,
        "password_hash": user.password_hash,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }
    data.update(overrides)
    return UserArchiveRecord.model_validate(data)


def archive(*records: UserArchiveRecord) -> UserArchive:
    return UserArchive(exported_at=datetime.now(timezone.utc), users=list(records))


@pytest.mark.asyncio
async def test_export_users_includes_every_user_column() -> None:
    admin = make_user(email="admin@example.com", role=UserRole.ADMIN)
    member = make_user(email="member@example.com", is_active=False)
    db = FakeDb([member, admin])
    response = Response()

    result = await export_users(response, db, admin)

    exported = {record.id: record for record in result.users}
    assert result.format == "sharekhan-copy-trader.users"
    assert result.version == 1
    assert exported[member.id].email == member.email
    assert exported[member.id].password_hash == member.password_hash
    assert exported[member.id].role == member.role
    assert exported[member.id].is_active is False
    assert exported[member.id].created_at == member.created_at
    assert exported[member.id].updated_at == member.updated_at
    assert response.headers["content-disposition"].endswith('.json"')
    assert response.headers["cache-control"] == "no-store"
    assert db.commits == 1


@pytest.mark.asyncio
async def test_import_users_creates_updates_and_leaves_identical_rows() -> None:
    admin = make_user(email="admin@example.com", role=UserRole.ADMIN)
    changed = make_user(email="old@example.com")
    imported_updated_at = changed.updated_at + timedelta(minutes=5)
    new_id = uuid.uuid4()
    new_created_at = datetime.now(timezone.utc).replace(microsecond=0)
    db = FakeDb([admin, changed])
    payload = archive(
        archive_record(admin),
        archive_record(changed, email="new@example.com", is_active=False, updated_at=imported_updated_at),
        UserArchiveRecord(
            id=new_id,
            email="created@example.com",
            password_hash=VALID_HASH,
            role=UserRole.USER,
            is_active=True,
            created_at=new_created_at,
            updated_at=new_created_at,
        ),
    )

    result = await import_users(payload, db, admin)

    assert result.model_dump() == {"total": 3, "created": 1, "updated": 1, "unchanged": 1}
    assert changed.email == "new@example.com"
    assert changed.is_active is False
    assert changed.updated_at == imported_updated_at
    created = next(user for user in db.users if user.id == new_id)
    assert created.password_hash == VALID_HASH
    assert created.created_at == new_created_at
    assert db.flushes == 1
    assert db.commits == 1


@pytest.mark.asyncio
async def test_import_rejects_email_owned_by_another_id() -> None:
    admin = make_user(email="admin@example.com", role=UserRole.ADMIN)
    existing = make_user(email="existing@example.com")
    db = FakeDb([admin, existing])
    payload = archive(
        archive_record(admin),
        UserArchiveRecord(
            id=uuid.uuid4(),
            email=existing.email,
            password_hash=VALID_HASH,
            role=UserRole.USER,
            is_active=True,
            created_at=existing.created_at,
            updated_at=existing.updated_at,
        ),
    )

    with pytest.raises(HTTPException) as exc:
        await import_users(payload, db, admin)

    assert exc.value.status_code == 409
    assert db.commits == 0


@pytest.mark.asyncio
async def test_import_cannot_lock_out_current_admin() -> None:
    admin = make_user(email="admin@example.com", role=UserRole.ADMIN)
    db = FakeDb([admin])
    payload = archive(archive_record(admin, role=UserRole.USER, is_active=False))

    with pytest.raises(HTTPException) as exc:
        await import_users(payload, db, admin)

    assert exc.value.status_code == 400
    assert "current administrator" in str(exc.value.detail)


def test_user_archive_rejects_plaintext_passwords_and_duplicate_emails() -> None:
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError, match="bcrypt"):
        UserArchiveRecord(
            id=uuid.uuid4(),
            email="user@example.com",
            password_hash="plaintext-password".ljust(60, "x"),
            role=UserRole.USER,
            is_active=True,
            created_at=now,
            updated_at=now,
        )

    first = UserArchiveRecord(
        id=uuid.uuid4(),
        email="duplicate@example.com",
        password_hash=VALID_HASH,
        role=UserRole.USER,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    second = first.model_copy(update={"id": uuid.uuid4()})
    with pytest.raises(ValidationError, match="duplicate user emails"):
        archive(first, second)
