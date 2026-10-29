"""JWT auth + role/company scoping. Scoping is enforced here, not in the UI or the LLM."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings


class Role(StrEnum):
    ADMIN = "admin"
    EDITOR = "editor"  # may enter manual KPIs
    VIEWER = "viewer"


@dataclass(frozen=True)
class Principal:
    user_id: str
    role: Role
    company_ids: frozenset[int] | None  # None = group-wide

    def can_see(self, company_id: int) -> bool:
        return self.company_ids is None or company_id in self.company_ids

    def require_company(self, company_id: int) -> None:
        if not self.can_see(company_id):
            raise HTTPException(403, "No access to this company")


_bearer = HTTPBearer(auto_error=True)


def make_token(user_id: str, role: Role, company_ids: list[int] | None = None) -> str:
    return jwt.encode(
        {"sub": user_id, "role": role.value, "companies": company_ids},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def get_principal(cred: HTTPAuthorizationCredentials = Depends(_bearer)) -> Principal:
    try:
        claims = jwt.decode(cred.credentials, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        companies = claims.get("companies")
        return Principal(
            claims["sub"], Role(claims["role"]), None if companies is None else frozenset(companies)
        )
    except (jwt.PyJWTError, KeyError, ValueError) as e:
        raise HTTPException(401, "Invalid token") from e


def require_editor(p: Principal = Depends(get_principal)) -> Principal:
    if p.role not in (Role.EDITOR, Role.ADMIN):
        raise HTTPException(403, "Editor role required")
    return p


def require_admin(p: Principal = Depends(get_principal)) -> Principal:
    if p.role is not Role.ADMIN:
        raise HTTPException(403, "Admin role required")
    return p
