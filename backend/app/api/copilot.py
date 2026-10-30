from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker
from sse_starlette.sse import EventSourceResponse
from starlette.background import BackgroundTask

from app.alerts import prefs as prefs_mod
from app.api.workflows import get_session_factory
from app.assets import service as asset_service
from app.assets.service import AssetError
from app.capabilities.copilot_tools import eligible_tools
from app.copilot import delegate as delegate_mod
from app.copilot.orchestrator import chat_turn
from app.core.config import settings
from app.core.security import Principal, get_principal
from app.db.models import ApprovalRequest, ChatMessage, ChatSession
from app.db.session import get_db
from app.memory import extract as memory_extract
from app.memory import store as memory_store
from app.services.scorecard import current_period

router = APIRouter(prefix="/copilot")


def get_anthropic():
    if not settings.anthropic_api_key:
        raise HTTPException(503, "Copilot is not configured (ANTHROPIC_API_KEY)")
    from anthropic import AsyncAnthropic

    return AsyncAnthropic(api_key=settings.anthropic_api_key)


class ChatRequest(BaseModel):
    message: str = Field(default="", max_length=8000)  # may be empty only when running a skill
    session_id: int | None = None
    skill_key: str | None = None
    skill_inputs: dict | None = None
    agent_key: str | None = None
    allow_draft: bool = False  # admins only: try an unpublished version
    period: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


def _own_session(db: Session, who: Principal, session_id: int) -> ChatSession:
    s = db.get(ChatSession, session_id)
    if s is None or s.user_id != who.user_id:  # sessions never cross users
        raise HTTPException(404, "Session not found")
    return s


@router.post("/chat")
async def chat(req: ChatRequest, db: Session = Depends(get_db), who: Principal = Depends(get_principal),
               client=Depends(get_anthropic), factory: sessionmaker = Depends(get_session_factory)):
    if req.skill_key and req.agent_key:
        raise HTTPException(422, "Use either a skill or an agent, not both")
    spec = None
    try:
        if req.skill_key:
            spec = asset_service.resolve(db, who, "skill", req.skill_key, req.skill_inputs, req.allow_draft)
        elif req.agent_key:
            spec = asset_service.resolve(db, who, "agent", req.agent_key, None, req.allow_draft)
    except AssetError as e:
        raise HTTPException(e.status, e.message) from e
    message = req.message.strip() or (f'Run the "{spec.label}" skill.' if req.skill_key and spec else "")
    if not message:
        raise HTTPException(422, "message is required")
    session = _own_session(db, who, req.session_id) if req.session_id else None
    if session is None:
        session = ChatSession(user_id=who.user_id, title=(spec.label if spec else message)[:80])
        db.add(session)
        db.flush()
    prior = list(db.scalars(select(ChatMessage).where(ChatMessage.session_id == session.id)
                            .order_by(ChatMessage.id)))
    history = [{"role": m.role, "content": m.content} for m in prior]
    db.add(ChatMessage(session_id=session.id, role="user", content=message))
    db.commit()
    sid = session.id
    # What the Copilot remembers from this user's earlier sessions: quoted data in the user turn, never in the
    # cached system prompt. Skills are scripted tasks, so they neither read nor write memory.
    remembering = not req.skill_key and prefs_mod.get(db, who.user_id).memory_enabled
    memory_block = memory_store.prompt_block(memory_store.recent(db, who.user_id)) if remembering else None
    outcome: dict = {"ok": False, "text": ""}
    # Registry capabilities an admin has allowed for this user's role. Scripted skills and agents keep their own tool lists.
    cap_tools = eligible_tools(db, who) if spec is None else {}
    # Only a supervisor may delegate, and only to the roster it declared and an admin approved.
    budget = delegate_mod.new_budget(spec.delegates_to) if spec and spec.supervisor else None

    async def remember() -> None:
        """Runs after the response has been sent, so it can never slow or break the chat."""
        if not (remembering and outcome["ok"] and len(outcome["text"]) >= 40):
            return
        items = await memory_extract.extract(client, message, outcome["text"])
        if items:
            def save() -> None:
                with factory() as mdb:
                    memory_store.remember(mdb, who.user_id, sid, items)
            await asyncio.to_thread(save)

    async def events():
        text, tools = [], []
        try:
            async for ev in chat_turn(client, db, who, history, message, req.period or current_period(), sid,
                                      spec.extra_system if spec else None, spec.tool_names if spec else None,
                                      spec.model if spec else None, memory_block, cap_tools,
                                      delegation=budget):
                if ev["type"] == "chunk":
                    text.append(ev["content"])
                    yield {"data": json.dumps({**ev, "session_id": sid})}
                else:
                    tools.append(ev["name"])
                    yield {"data": json.dumps({**ev, "session_id": sid})}
            db.add(ChatMessage(session_id=sid, role="assistant", content="".join(text), tool_calls=tools))
            db.commit()
            outcome.update(ok=True, text="".join(text))
            yield {"data": json.dumps({"type": "done", "session_id": sid})}
        except Exception:  # noqa: BLE001 - never echo internals to the client
            yield {"data": json.dumps({"type": "error", "message": "The Copilot hit an error."})}

    return EventSourceResponse(events(), ping=15, background=BackgroundTask(remember))


@router.get("/sessions")
def sessions(q: str | None = None, db: Session = Depends(get_db), who: Principal = Depends(get_principal)):
    """Your sessions, newest first. `q` matches the title or any message in the conversation."""
    stmt = select(ChatSession).where(ChatSession.user_id == who.user_id)
    if q and q.strip():
        like = f"%{q.strip().lower()}%"
        in_msgs = select(ChatMessage.session_id).where(func.lower(ChatMessage.content).like(like))
        stmt = stmt.where(func.lower(ChatSession.title).like(like) | ChatSession.id.in_(in_msgs))
    rows = list(db.scalars(stmt.order_by(ChatSession.id.desc()).limit(100)))
    stats = {sid: (n, last) for sid, n, last in db.execute(
        select(ChatMessage.session_id, func.count(ChatMessage.id), func.max(ChatMessage.created_at))
        .where(ChatMessage.session_id.in_([s.id for s in rows])).group_by(ChatMessage.session_id))} if rows else {}
    return [{"id": s.id, "title": s.title, "created_at": s.created_at,
             "message_count": stats.get(s.id, (0, None))[0], "last_at": stats.get(s.id, (0, s.created_at))[1] or s.created_at}
            for s in rows]


@router.get("/sessions/{session_id}")
def session_messages(session_id: int, db: Session = Depends(get_db), who: Principal = Depends(get_principal)):
    s = _own_session(db, who, session_id)
    rows = db.scalars(select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.id))
    approvals = db.scalars(select(ApprovalRequest).where(ApprovalRequest.session_id == session_id).order_by(ApprovalRequest.id))
    return {"id": s.id, "title": s.title, "created_at": s.created_at,
            "messages": [{"role": m.role, "content": m.content, "tools": m.tool_calls, "at": m.created_at} for m in rows],
            "approvals": [{"id": a.id, "action": a.action, "summary": a.summary, "status": a.status} for a in approvals]}
