"""Workspace company profile + lightweight interview onboarding."""
from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.company.profile import CompanyProfile, load_profile, save_profile
from app.core.config import settings
from app.core.security import Principal, get_principal, require_admin

router = APIRouter(tags=["company-profile"])

# In-memory interview sessions (single-instance API, same constraint as scheduler).
_SESSIONS: dict[str, dict[str, Any]] = {}

_OPENING = (
    "Tell me about your company — what you do, who you sell to, roughly how "
    "big you are, and what you're focused on this year."
)

_INTERVIEW_SYSTEM = """You help set up a company profile for an executive AI.
Given the conversation so far, either ask ONE clarifying question OR emit a draft.
Return ONLY JSON of one of these shapes:
{"type":"question","question":"...","options":["..."]}
{"type":"draft","profile":{...CompanyProfile fields...},"summary":"..."}
Keep questions under 4 total. Prefer drafting when you have enough."""


@router.get("/company-profile")
def get_profile(_who: Principal = Depends(get_principal)) -> dict:
    p = load_profile()
    return {"profile": p.model_dump(), "empty": p.is_empty(), "path": str(settings.company_profile_path)}


@router.put("/company-profile")
def put_profile(
    body: CompanyProfile,
    _who: Principal = Depends(require_admin),
) -> dict:
    save_profile(body)
    return {"profile": body.model_dump(), "empty": body.is_empty()}


class InterviewStartOut(BaseModel):
    session_id: str
    opening: str


@router.post("/onboard/interview/start")
def interview_start(_who: Principal = Depends(require_admin)) -> InterviewStartOut:
    sid = uuid.uuid4().hex
    existing = load_profile()
    _SESSIONS[sid] = {
        "turns": [],
        "questions": 0,
        "existing": existing.model_dump() if not existing.is_empty() else None,
    }
    return InterviewStartOut(session_id=sid, opening=_OPENING)


class InterviewMessageIn(BaseModel):
    session_id: str
    message: str = Field(min_length=1, max_length=8000)
    force_draft: bool = False


@router.post("/onboard/interview/message")
async def interview_message(
    body: InterviewMessageIn,
    _who: Principal = Depends(require_admin),
) -> dict:
    sess = _SESSIONS.get(body.session_id)
    if sess is None:
        raise HTTPException(404, "interview session not found")
    sess["turns"].append({"role": "user", "text": body.message})

    if not settings.anthropic_api_key:
        # Deterministic fallback: treat the message as a free-text name/mission dump.
        draft = CompanyProfile(
            name=body.message.strip().split("\n")[0][:120] or "My Company",
            mission=body.message.strip()[:2000],
        )
        sess["draft"] = draft.model_dump()
        return {"type": "draft", "profile": draft.model_dump(), "summary": "Draft from your description."}

    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    transcript = "\n".join(f"{t['role']}: {t['text']}" for t in sess["turns"][-12:])
    hint = ""
    if sess.get("existing"):
        hint = f"Existing profile:\n{json.dumps(sess['existing'])}\n\n"
    force = body.force_draft or sess["questions"] >= 4
    user = (
        f"{hint}Transcript:\n{transcript}\n\n"
        + ("Emit a draft now." if force else "Ask a question or emit a draft.")
    )
    resp = await client.messages.create(
        model=settings.routing_model,
        max_tokens=2000,
        system=_INTERVIEW_SYSTEM,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise HTTPException(502, "interview model returned no JSON")
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError as e:
        raise HTTPException(502, "interview model returned invalid JSON") from e

    if payload.get("type") == "question":
        sess["questions"] += 1
        q = str(payload.get("question") or "Could you say more?")
        sess["turns"].append({"role": "assistant", "text": q})
        return {
            "type": "question",
            "question": q,
            "options": list(payload.get("options") or [])[:4],
            "questions_asked": sess["questions"],
        }

    profile_data = payload.get("profile") or {}
    try:
        draft = CompanyProfile.model_validate(profile_data)
    except Exception as e:
        raise HTTPException(422, f"invalid draft profile: {e}") from e
    sess["draft"] = draft.model_dump()
    return {
        "type": "draft",
        "profile": draft.model_dump(),
        "summary": str(payload.get("summary") or ""),
    }


class InterviewCommitIn(BaseModel):
    session_id: str
    profile: CompanyProfile | None = None


@router.post("/onboard/interview/commit")
def interview_commit(
    body: InterviewCommitIn,
    _who: Principal = Depends(require_admin),
) -> dict:
    sess = _SESSIONS.get(body.session_id)
    if sess is None:
        raise HTTPException(404, "interview session not found")
    if body.profile is not None:
        profile = body.profile
    elif sess.get("draft"):
        profile = CompanyProfile.model_validate(sess["draft"])
    else:
        raise HTTPException(422, "no draft to commit")
    if profile.is_empty():
        raise HTTPException(422, "profile name is required")
    save_profile(profile)
    _SESSIONS.pop(body.session_id, None)
    return {"ok": True, "profile": profile.model_dump()}
