from datetime import datetime, timezone

from sqlalchemy import String, Text, Float, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.conversation_engine import Base


def utc_now() -> datetime:
    """Helper so every timestamp is saved in UTC, not server-local time."""
    return datetime.now(timezone.utc)

    
class Conversation(Base):
    __tablename__ = "conversations"

    # Real primary key. Auto-increments on its own (1, 2, 3, ...).
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Groups multiple messages that belong to the same chat session.
    # (NOT unique on its own - one session_id can appear on many rows.)
    session_id: Mapped[str] = mapped_column(String(64), index=True)

    user_message: Mapped[str] = mapped_column(Text)
    assistant_message: Mapped[str] = mapped_column(Text)

    # One of: "general", "faq", "pricing", "technical"
    intent: Mapped[str] = mapped_column(String(32), index=True)

    created_at: Mapped[datetime] = mapped_column(default=utc_now)

    # Lets us write conversation.logs to get all related execution_logs rows.
    logs: Mapped[list["ExecutionLog"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
    )


class ExecutionLog(Base):
    __tablename__ = "execution_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Points to conversations.id - links this log to the exact message it belongs to.
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        index=True,
    )

    execution_time: Mapped[float] = mapped_column(Float)   # total time, in seconds
    # A pending pricing turn bypasses the intent router, so this is legitimately absent.
    router_time: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Free-form JSON, e.g. {"similarity_score": 0.71, "chunks_used": 3}
    rag_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # "success" or "failed" - filled in automatically, see note below.
    status: Mapped[str] = mapped_column(String(16), default="success")

    created_at: Mapped[datetime] = mapped_column(default=utc_now)

    conversation: Mapped["Conversation"] = relationship(back_populates="logs")
