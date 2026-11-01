"""Deprecated entrypoint — Executive owns the chat loop now."""
from app.orchestrator.executive import chat_turn

__all__ = ["chat_turn"]
