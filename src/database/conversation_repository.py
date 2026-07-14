from sqlalchemy.ext.asyncio import AsyncSession
from src.database.models import Conversation, ExecutionLog

async def save_conversation_turn(
    session: AsyncSession,
    *,
    session_id: str,
    user_message: str,
    assistant_message: str,
    intent: str,
    execution_time: float,
    router_time: float | None = None,
    rag_metadata: dict | None = None,
    error: str | None = None,
) -> Conversation:
    """
    Saves one full turn (user message + bot answer) AND its matching log row,
    in a single database transaction.
    """
    conversation = Conversation(
        session_id=session_id,
        user_message=user_message,
        assistant_message=assistant_message,
        intent=intent,
    )
    session.add(conversation)
    # flush() sends the INSERT to the db so conversation.id gets filled in,
    # WITHOUT fully closing the transaction yet (commit does that at the end).
    await session.flush()

    log = ExecutionLog(
        conversation_id=conversation.id,
        execution_time=execution_time,
        router_time=router_time,
        rag_metadata=rag_metadata,
        error=error,
        status="failed" if error else "success",
    )
    session.add(log)

    await session.commit()
    return conversation