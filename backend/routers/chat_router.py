"""
backend/routers/chat_router.py
------------------------------
Routes:
  POST /chat   → send a message; works for both guests and authenticated users.

Guest users get a response but nothing is persisted.
Authenticated users have their messages saved and context is loaded from DB.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend import models, schemas
from backend.auth import get_current_user_optional
from backend.rag_service import rag_service

router = APIRouter(prefix="/chat", tags=["chat"])


def _build_history(messages: list[models.Message]) -> list[tuple[str, str]]:
    """Convert DB Message objects to LangGraph-compatible (role, content) tuples."""
    return [(msg.role, msg.content) for msg in messages]


def _auto_title(text: str, max_len: int = 60) -> str:
    """Derive a short conversation title from the first user message."""
    title = text.strip().replace("\n", " ")
    return (title[:max_len] + "…") if len(title) > max_len else title


@router.post("", response_model=schemas.ChatResponse)
def chat(
    body: schemas.ChatRequest,
    payload: Optional[dict] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    user_id: Optional[str] = payload["sub"] if payload else None

    # ── Guest mode ────────────────────────────────────────────────────────────
    if user_id is None:
        try:
            answer = rag_service.chat(body.message, history=[])
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(exc),
            )
        return schemas.ChatResponse(answer=answer, conversation_id="guest")

    # ── Authenticated mode ────────────────────────────────────────────────────
    # 1. Resolve or create conversation
    if body.conversation_id and body.conversation_id != "guest":
        conv = (
            db.query(models.Conversation)
            .filter(
                models.Conversation.id == body.conversation_id,
                models.Conversation.user_id == user_id,
            )
            .first()
        )
        if not conv:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found.",
            )
    else:
        # Auto-create a new conversation titled from the first message
        conv = models.Conversation(
            user_id=user_id,
            title=_auto_title(body.message),
        )
        db.add(conv)
        db.flush()  # get the ID without committing yet

    # 2. Load prior messages for context
    prior_messages = (
        db.query(models.Message)
        .filter(models.Message.conversation_id == conv.id)
        .order_by(models.Message.created_at.asc())
        .all()
    )
    history = _build_history(prior_messages)

    # 3. Run RAG agent
    try:
        answer = rag_service.chat(body.message, history=history)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )


    # 4. Persist user message + assistant reply
    db.add(models.Message(
        conversation_id=conv.id,
        role="user",
        content=body.message,
    ))
    db.add(models.Message(
        conversation_id=conv.id,
        role="assistant",
        content=answer,
    ))
    # Touch conversation updated_at
    conv.updated_at = datetime.utcnow()
    db.commit()

    return schemas.ChatResponse(answer=answer, conversation_id=conv.id)
