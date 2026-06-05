import asyncio
import json
import logging
import os
import re
from typing import Any, Sequence

from dotenv import load_dotenv
from sqlalchemy.orm import Session as DBSession

from database.db import SessionLocal
from database.models import ChatMessage, ChatSession, UserProfile
from gemini_generation import generate_content_with_fallback, is_resource_exhausted

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """Analyze the conversation below between a User and Richard Feynman.

Extract implicit, persistent facts about the USER only (e.g. education level, topics they struggle with, learning preferences).
Do NOT extract facts about Richard Feynman.

Return ONLY a valid JSON array of short fact strings.
Example: ["User is an undergraduate physics student", "User struggles with calculus", "User prefers visual analogies"]
If there are no meaningful user facts, return [].

Conversation:
{conversation}
"""


def _format_messages_for_prompt(latest_messages: Sequence[Any]) -> str:
    lines: list[str] = []
    for msg in latest_messages:
        if isinstance(msg, ChatMessage):
            role, content = msg.role, msg.content
        elif isinstance(msg, dict):
            role, content = msg.get("role", "unknown"), msg.get("content", "")
        else:
            role, content = getattr(msg, "role", "unknown"), getattr(msg, "content", "")
        lines.append(f"{role.upper()}: {content}")
    return "\n".join(lines)


def _parse_facts_from_response(raw_text: str) -> list[str]:
    text = raw_text.strip()
    if not text:
        return []

    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [str(f).strip() for f in parsed if str(f).strip()]
    except json.JSONDecodeError:
        pass

    # Fallback: extract bullet lines if model did not return strict JSON
    facts: list[str] = []
    for line in text.splitlines():
        cleaned = re.sub(r"^[\s\-\*\d\.\)]+", "", line).strip()
        if cleaned and not cleaned.startswith("["):
            facts.append(cleaned)
    return facts


def _call_gemini_extraction(conversation: str) -> list[str]:
    try:
        prompt = EXTRACTION_PROMPT.format(conversation=conversation)
        raw_text = generate_content_with_fallback(prompt)
        return _parse_facts_from_response(raw_text)
    except Exception as exc:
        if is_resource_exhausted(exc):
            print(
                "Primary model quota exhausted during fact extraction. "
                "Skipping background memory update."
            )
            logger.warning("Fact extraction quota exhausted: %s", exc)
            return []
        print(f"Gemini fact-extraction call failed: {str(exc)}")
        raise


def get_or_create_chat_session(session_id: str | None = None) -> str:
    """Return an existing chat session id or create a new one."""
    db = SessionLocal()
    try:
        if session_id:
            existing = db.query(ChatSession).filter(ChatSession.id == session_id).first()
            if existing:
                return existing.id

        new_session = ChatSession()
        if session_id:
            new_session.id = session_id
        db.add(new_session)
        db.commit()
        db.refresh(new_session)
        return new_session.id
    finally:
        db.close()


def save_chat_message(session_id: str, role: str, content: str) -> ChatMessage:
    """Persist a single chat message and return the saved row."""
    db = SessionLocal()
    try:
        message = ChatMessage(session_id=session_id, role=role, content=content)
        db.add(message)
        db.commit()
        db.refresh(message)
        return message
    finally:
        db.close()


def get_recent_history(session_id: str, limit: int = 10) -> list[ChatMessage]:
    """Return the last N messages for a session (chronological order)."""
    db = SessionLocal()
    try:
        messages = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.timestamp.desc())
            .limit(limit)
            .all()
        )
        return messages[::-1]
    finally:
        db.close()


def get_user_facts(session_id: str, db: DBSession | None = None) -> list[str]:
    """Return all extracted facts for a session (for future prompt injection)."""
    own_session = db is None
    if own_session:
        db = SessionLocal()
    try:
        rows = (
            db.query(UserProfile)
            .filter(UserProfile.session_id == session_id)
            .order_by(UserProfile.timestamp.asc())
            .all()
        )
        return [row.extracted_fact for row in rows]
    finally:
        if own_session:
            db.close()


async def extract_and_store_user_facts(
    session_id: str,
    latest_messages: Sequence[Any],
) -> None:
    """
    Background-safe extraction: analyze recent messages and persist user facts.
    Never raises — failures are logged only.
    """
    try:
        if not latest_messages:
            return

        conversation = _format_messages_for_prompt(latest_messages)
        facts = await asyncio.to_thread(_call_gemini_extraction, conversation)

        if not facts:
            logger.info("No user facts extracted for session %s", session_id)
            return

        db = SessionLocal()
        try:
            for fact in facts:
                db.add(
                    UserProfile(
                        session_id=session_id,
                        extracted_fact=fact,
                    )
                )
            db.commit()
            logger.info(
                "Stored %d user fact(s) for session %s", len(facts), session_id
            )
        finally:
            db.close()
    except Exception as exc:
        logger.error(
            "Failed to extract/store user facts for session %s: %s",
            session_id,
            exc,
            exc_info=True,
        )
