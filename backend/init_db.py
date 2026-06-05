"""Create all SQLAlchemy tables for the Feynman memory system."""

from database.db import Base, engine
from database.models import ChatMessage, ChatSession, UserProfile  # noqa: F401


def init_database() -> None:
    Base.metadata.create_all(bind=engine)
    print(f"Database initialized at: {engine.url}")


if __name__ == "__main__":
    init_database()
