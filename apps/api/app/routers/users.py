from datetime import timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.audit import add_audit_log
from app.dependencies import DbSession, require_admin
from app.models import User, UserRole, utcnow
from app.schemas import UserArchive, UserArchiveRecord, UserImportResult

router = APIRouter(prefix="/users", tags=["users"])
AdminUser = Annotated[User, Depends(require_admin)]


def _archive_record(user: User) -> UserArchiveRecord:
    return UserArchiveRecord.model_validate(
        {
            "id": user.id,
            "email": user.email,
            "password_hash": user.password_hash,
            "role": user.role,
            "is_active": user.is_active,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
        }
    )


def _record_changed(user: User, record: UserArchiveRecord) -> bool:
    return any(
        (
            user.email != record.email,
            user.password_hash != record.password_hash,
            user.role != record.role,
            user.is_active != record.is_active,
            user.created_at != record.created_at,
            user.updated_at != record.updated_at,
        )
    )


def _apply_record(user: User, record: UserArchiveRecord) -> None:
    user.email = record.email
    user.password_hash = record.password_hash
    user.role = record.role
    user.is_active = record.is_active
    user.created_at = record.created_at
    user.updated_at = record.updated_at


def _validate_import_conflicts(
    archive: UserArchive,
    existing_users: list[User],
    admin: User,
) -> None:
    existing_by_email = {user.email.lower(): user for user in existing_users}

    for record in archive.users:
        email_match = existing_by_email.get(record.email.lower())
        if email_match and email_match.id != record.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Email {record.email} belongs to a different user id",
            )
        if record.id == admin.id and (record.role != UserRole.ADMIN or not record.is_active):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Import cannot deactivate or demote the current administrator",
            )


@router.get("/export", response_model=UserArchive)
async def export_users(response: Response, db: DbSession, admin: AdminUser) -> UserArchive:
    users = list((await db.scalars(select(User).order_by(User.email.asc()))).all())
    if not users:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No users found")

    exported_at = utcnow()
    archive = UserArchive(
        exported_at=exported_at,
        users=[_archive_record(user) for user in users],
    )
    filename_timestamp = exported_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    response.headers["Content-Disposition"] = (
        f'attachment; filename="sharekhan-copy-trader-users-{filename_timestamp}.json"'
    )
    response.headers["Cache-Control"] = "no-store"
    await add_audit_log(
        db,
        action="users.export",
        entity_type="user_archive",
        user_id=admin.id,
        metadata={"user_count": len(users), "version": archive.version},
    )
    await db.commit()
    return archive


@router.post("/import", response_model=UserImportResult)
async def import_users(archive: UserArchive, db: DbSession, admin: AdminUser) -> UserImportResult:
    existing_users = list((await db.scalars(select(User))).all())
    _validate_import_conflicts(archive, existing_users, admin)
    existing_by_id = {user.id: user for user in existing_users}

    created = 0
    updated = 0
    unchanged = 0
    for record in archive.users:
        user = existing_by_id.get(record.id)
        if user is None:
            user = User(id=record.id)
            _apply_record(user, record)
            db.add(user)
            existing_by_id[user.id] = user
            created += 1
        elif _record_changed(user, record):
            _apply_record(user, record)
            updated += 1
        else:
            unchanged += 1

    await db.flush()
    result = UserImportResult(
        total=len(archive.users),
        created=created,
        updated=updated,
        unchanged=unchanged,
    )
    await add_audit_log(
        db,
        action="users.import",
        entity_type="user_archive",
        user_id=admin.id,
        metadata={**result.model_dump(), "version": archive.version},
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User import conflicted with an existing user",
        ) from exc
    return result
