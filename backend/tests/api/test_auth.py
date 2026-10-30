from fastapi.security import HTTPAuthorizationCredentials

from app.core.security import Role, get_principal

from .conftest import client  # noqa: F401


def test_login_any_credentials_returns_admin_token(client):
    r = client.post("/auth/login", json={"email": "demo@example.com", "password": "anything"})
    assert r.status_code == 200
    token = r.json()["token"]
    who = get_principal(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))
    assert who.user_id == "demo@example.com"
    assert who.role is Role.ADMIN
    assert who.company_ids is None
    assert client.get("/companies", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_login_requires_email_and_password(client):
    assert client.post("/auth/login", json={"email": "", "password": "x"}).status_code == 422
    assert client.post("/auth/login", json={"email": "a@b.c"}).status_code == 422
