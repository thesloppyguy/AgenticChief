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
from app.core.config import settings
from app.core.security import Principal, get_principal
from app.db.models import ApprovalRequest, ChatMessage, ChatSession
from app.db.session import get_db
from app.memory import extract as memory_extract
from app.memory import store as memory_store
from app.orchestrator.executive import chat_turn
from app.services.scorecard import current_period

router = APIRouter(prefix="/copilot")


def get_anthropic():
    if not settings.anthropic_api_key:
        raise HTTPException(503, "Copilot is not configured (ANTHROPIC_API_KEY)")
    from anthropic import AsyncAnthropic

    return AsyncAnthropic(api_key=settings.anthropic_api_key)


class ChatRequest(BaseModel):
    message: str = Field(default="", max_length=8000)
    session_id: int | None = None
    skill_name: str | None = None  # Markdown skill to load into the first user turn
    skill_key: str | None = None  # alias used by older frontend callers
    agent_key: str | None = None  # preferred specialist hint (injected into the user turn)
    period: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


def _own_session(db: Session, who: Principal, session_id: int) -> ChatSession:
    s = db.get(ChatSession, session_id)
    if s is None or s.user_id != who.user_id:
        raise HTTPException(404, "Session not found")
    return s


@router.post("/chat")
async def chat(
    req: ChatRequest,
    db: Session = Depends(get_db),
    who: Principal = Depends(get_principal),
    client=Depends(get_anthropic),
    factory: sessionmaker = Depends(get_session_factory),
):
    message = req.message.strip()
    skill_name = req.skill_name or req.skill_key
    if skill_name:
        from app.knowledge.skills_repo import SkillNotFoundError, get_skill

        try:
            skill = get_skill(skill_name)
        except SkillNotFoundError as e:
            raise HTTPException(404, str(e)) from e
        playbook = (
            f"Follow the playbook `{skill.frontmatter.name}`:\n\n{skill.body}\n\n"
            f"User request: {message or skill.frontmatter.description}"
        )
        message = playbook
        title_seed = skill.frontmatter.name
    else:
        title_seed = message
    if req.agent_key:
        message = (
            f"<preferred_specialist>{req.agent_key}</preferred_specialist>\n"
            f"{message}"
        )
    if not message:
        raise HTTPException(422, "message is required")

    session = _own_session(db, who, req.session_id) if req.session_id else None
    if session is None:
        session = ChatSession(user_id=who.user_id, title=title_seed[:80])
        db.add(session)
        db.flush()
    prior = list(
        db.scalars(
            select(ChatMessage)
            .where(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.id)
        )
    )
    history = [{"role": m.role, "content": m.content} for m in prior]
    db.add(ChatMessage(session_id=session.id, role="user", content=message))
    db.commit()
    sid = session.id
    remembering = prefs_mod.get(db, who.user_id).memory_enabled
    memory_block = (
        memory_store.prompt_block(memory_store.recent(db, who.user_id)) if remembering else None
    )
    outcome: dict = {"ok": False, "text": ""}

    async def remember() -> None:
        if not (remembering and outcome["ok"] and len(outcome["text"]) >= 40):
            return
        items = await memory_extract.extract(client, message, outcome["text"])
        if items:

            def save() -> None:
                with factory() as mdb:
                    memory_store.remember(mdb, who.user_id, sid, items)

            await asyncio.to_thread(save)

    async def events():
        # Emit the session id immediately so the client can route to /chat/{id}
        # before the model starts streaming.
        yield {"data": json.dumps({"type": "session", "session_id": sid})}
        text, tools, artifacts = [], [], []
        try:
            async for ev in chat_turn(
                client,
                db,
                who,
                history,
                message,
                req.period or current_period(),
                sid,
                memory_block=memory_block,
            ):
                if ev["type"] == "chunk":
                    text.append(ev["content"])
                    yield {"data": json.dumps({**ev, "session_id": sid})}
                elif ev["type"] == "artifact":
                    art = ev.get("artifact")
                    if isinstance(art, dict):
                        artifacts.append(art)
                    yield {"data": json.dumps({**ev, "session_id": sid})}
                else:
                    tools.append(ev.get("name"))
                    yield {"data": json.dumps({**ev, "session_id": sid})}
            db.add(
                ChatMessage(
                    session_id=sid,
                    role="assistant",
                    content="".join(text),
                    tool_calls=tools,
                    artifacts=artifacts or None,
                )
            )
            db.commit()
            outcome.update(ok=True, text="".join(text))
            yield {"data": json.dumps({"type": "done", "session_id": sid})}
        except Exception:  # noqa: BLE001
            yield {"data": json.dumps({"type": "error", "message": "The Copilot hit an error."})}

    async def after_chat() -> None:
        await remember()
        if not (outcome["ok"] and len(outcome["text"]) >= 40):
            return
        try:
            from app.memory import history_chat

            await history_chat.schedule_chat_notes(
                factory, client, who.user_id, sid, message, outcome["text"]
            )
        except Exception:  # noqa: BLE001
            pass
        try:
            from app.memory import open_loops

            await open_loops.schedule_open_loop_pass(
                factory, client, who.user_id, sid, message, outcome["text"]
            )
        except Exception:  # noqa: BLE001
            pass

    return EventSourceResponse(events(), ping=15, background=BackgroundTask(after_chat))


@router.get("/sessions")
def sessions(
    q: str | None = None,
    limit: int = 30,
    cursor: str | None = None,
    db: Session = Depends(get_db),
    who: Principal = Depends(get_principal),
):
    limit = min(max(limit, 1), 100)
    stmt = select(ChatSession).where(ChatSession.user_id == who.user_id)
    if q and q.strip():
        like = f"%{q.strip().lower()}%"
        in_msgs = select(ChatMessage.session_id).where(func.lower(ChatMessage.content).like(like))
        stmt = stmt.where(func.lower(ChatSession.title).like(like) | ChatSession.id.in_(in_msgs))
    if cursor and cursor.isdigit():
        stmt = stmt.where(ChatSession.id < int(cursor))
    rows = list(db.scalars(stmt.order_by(ChatSession.id.desc()).limit(limit + 1)))
    more = len(rows) > limit
    rows = rows[:limit]
    stats = (
        {
            sid: (n, last)
            for sid, n, last in db.execute(
                select(
                    ChatMessage.session_id,
                    func.count(ChatMessage.id),
                    func.max(ChatMessage.created_at),
                )
                .where(ChatMessage.session_id.in_([s.id for s in rows]))
                .group_by(ChatMessage.session_id)
            )
        }
        if rows
        else {}
    )
    items = [
        {
            "id": s.id,
            "title": s.title,
            "created_at": s.created_at,
            "message_count": stats.get(s.id, (0, None))[0],
            "last_at": stats.get(s.id, (0, s.created_at))[1] or s.created_at,
        }
        for s in rows
    ]
    return {"items": items, "next_cursor": str(rows[-1].id) if more else None}


@router.get("/sessions/{session_id}")
def session_messages(
    session_id: int, db: Session = Depends(get_db), who: Principal = Depends(get_principal)
):
    s = _own_session(db, who, session_id)
    rows = db.scalars(
        select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.id)
    )
    approvals = db.scalars(
        select(ApprovalRequest)
        .where(ApprovalRequest.session_id == session_id)
        .order_by(ApprovalRequest.id)
    )
    return {
        "id": s.id,
        "title": s.title,
        "created_at": s.created_at,
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "tools": m.tool_calls,
                "artifacts": m.artifacts,
                "at": m.created_at,
            }
            for m in rows
        ],
        "approvals": [
            {"id": a.id, "action": a.action, "summary": a.summary, "status": a.status}
            for a in approvals
        ],
    }
