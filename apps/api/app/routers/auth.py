from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.audit import add_audit_log
from app.dependencies import CurrentUser, DbSession
from app.models import User
from app.schemas import LoginRequest, Token, UserCreate, UserRead
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, db: DbSession) -> User:
    existing = await db.scalar(select(User).where(User.email == payload.email.lower()))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered")
    user = User(email=payload.email.lower(), password_hash=hash_password(payload.password))
    db.add(user)
    await db.flush()
    await add_audit_log(db, action="account.register", entity_type="user", entity_id=user.id, user_id=user.id)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=Token)
async def login(payload: LoginRequest, db: DbSession) -> Token:
    user = await db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    token = create_access_token(str(user.id), user.role.value)
    await add_audit_log(db, action="auth.login", entity_type="user", entity_id=user.id, user_id=user.id)
    await db.commit()
    return Token(access_token=token)


@router.get("/me", response_model=UserRead)
async def me(current_user: CurrentUser) -> User:
    return current_user

