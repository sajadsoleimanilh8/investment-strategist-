"""Web authentication contracts.

The password is write-only: it appears in `SignupIn` and `LoginIn` and in no
response model anywhere, which is what keeps it out of a serialised body by
construction rather than by remembering.
"""
from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field

#: Long enough to matter, short enough that argon2 stays fast. There is no
#: composition rule: length beats character classes, and a rule people work
#: around produces worse passwords than none.
MIN_PASSWORD_LENGTH = 10


class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=256)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=1)


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str = Field(min_length=1, max_length=256)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=256)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int          # seconds until the access token expires


class MeOut(BaseModel):
    id: int
    email: str | None = None
    telegram_id: int | None = None
    locale: str
    risk_profile: str | None = None
    onboarded: bool
