from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import Token, UserLogin, UserOut, UserRegister
from app.services.auth_service import (
    create_access_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(body: UserRegister, db: AsyncSession = Depends(get_db)):
    """
    Create a new account.

    Returns the new user (never the password hash). Returns 409 if the email is
    already taken — we check first for a clean message, and the DB's unique
    constraint is the real backstop against a race between two registrations.
    """
    existing = await db.scalar(select(User).where(User.email == body.email))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    user = User(email=body.email, hashed_password=hash_password(body.password))
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as exc:
        # Lost a race with a concurrent registration for the same email — the
        # pre-check passed for both, but the unique constraint caught the second.
        # Turn the DB error into the same clean 409 instead of a 500.
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        ) from exc
    await db.refresh(user)

    return UserOut.model_validate(user)


@router.post("/login", response_model=Token)
async def login(body: UserLogin, db: AsyncSession = Depends(get_db)):
    """
    Exchange email + password for a signed access token.

    Returns 401 on any failure — wrong email or wrong password give the SAME
    message ("Incorrect email or password") so an attacker can't probe which
    emails are registered.
    """
    user = await db.scalar(select(User).where(User.email == body.email))

    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return Token(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut)
async def read_me(current_user: User = Depends(get_current_user)):
    """Return the currently logged-in user — handy for the frontend to confirm
    a stored token is still valid after a page refresh."""
    return UserOut.model_validate(current_user)
