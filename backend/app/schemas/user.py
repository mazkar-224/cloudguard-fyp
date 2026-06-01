from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserRegister(BaseModel):
    """Body for POST /auth/register.

    EmailStr validates the address shape (rejects "not-an-email") before we
    ever touch the DB. The password has a minimum length so we don't store
    trivially weak credentials; bcrypt handles the upper bound.
    """

    email: EmailStr
    password: str = Field(min_length=8, max_length=128, description="At least 8 characters")


class UserLogin(BaseModel):
    """Body for POST /auth/login. No length rules here — we only check the
    credentials against what's stored, and we don't want to leak password
    policy through validation errors on the login form."""

    email: EmailStr
    password: str


class UserOut(BaseModel):
    """A user as returned by the API — never includes the password hash."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    created_at: datetime


class Token(BaseModel):
    """The login response. `token_type` is always "bearer" — the frontend
    sends it back as `Authorization: Bearer <access_token>`."""

    access_token: str
    token_type: str = "bearer"
