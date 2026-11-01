"""Choose Google or Microsoft for mail/calendar based on env (OE pattern)."""
from __future__ import annotations

import os
from typing import Literal

Provider = Literal["google", "microsoft", "none"]


def mail_provider() -> Provider:
    if os.environ.get("GOOGLE_OAUTH_CLIENT_ID") or os.environ.get("USER_GOOGLE_EMAIL"):
        return "google"
    if os.environ.get("MS365_MCP_CLIENT_ID"):
        return "microsoft"
    return "none"


def calendar_provider() -> Provider:
    return mail_provider()


def status() -> dict[str, str]:
    return {"mail": mail_provider(), "calendar": calendar_provider()}
