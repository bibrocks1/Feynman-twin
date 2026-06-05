from sqlalchemy.orm import Session as DBSession
from database.models import Message, Session
from database.db import Base, engine

# Ensure tables exist
Base.metadata.create_all(bind=engine)

def get_or_create_session(db: DBSession, session_id: str = None) -> str:
    """Returns an existing session ID or creates a new one."""
    if session_id:
        existing = db.query(Session).filter(Session.id == session_id).first()
        if existing:
            return existing.id
            
    new_session = Session()
    if session_id:
        new_session.id = session_id
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    return new_session.id

def add_message(db: DBSession, session_id: str, role: str, content: str):
    """Appends a new message to the session."""
    msg = Message(session_id=session_id, role=role, content=content)
    db.add(msg)
    db.commit()

def get_recent_messages(db: DBSession, session_id: str, limit: int = 10) -> list:
    """Retrieves the last N messages for a given session."""
    messages = db.query(Message)\
        .filter(Message.session_id == session_id)\
        .order_by(Message.timestamp.desc())\
        .limit(limit)\
        .all()
    # Return chronologically
    return messages[::-1]
