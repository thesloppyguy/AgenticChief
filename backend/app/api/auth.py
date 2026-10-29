"""Demo sign-in. Accepts any email/password and returns a group-wide admin JWT."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.security import Role, make_token

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str = Field(min_length=1)
    password: str = Field(min_length=1)


class LoginResponse(BaseModel):
    token: str


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest) -> LoginResponse:
    # Demo only: credentials are not checked. SSO replaces this.
    return LoginResponse(token=make_token(body.email.strip(), Role.ADMIN, None))
