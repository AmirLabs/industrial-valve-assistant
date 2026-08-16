from sqlalchemy.ext.asyncio import AsyncSession
from src.database.models import Conversation, ExecutionLog, TokenUsage, DebugTraceRecord
from src.database.debug_trace import DebugTrace
from src.config.model_prices import get_model_price

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


async def save_token_usage(
    session: AsyncSession,
    *,
    conversation_id: int,
    step: str,
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> TokenUsage:
    """
    Saves one model call's token usage AND its dollar cost.

    You give it the easy things the API returns (token counts). This helper
    looks up the model price, does the money math, and fills every column.
    Call it once per model call - so a turn with a router call plus a handler
    call ends up with two rows.
    """
    # Look up this model's price. Prices are per 1,000,000 tokens.
    price = get_model_price(model_name)

    prompt_cost = prompt_tokens / 1_000_000 * price["input"]
    completion_cost = completion_tokens / 1_000_000 * price["output"]

    usage = TokenUsage(
        conversation_id=conversation_id,
        step=step,
        model_name=model_name,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        prompt_cost=prompt_cost,
        completion_cost=completion_cost,
        total_cost=prompt_cost + completion_cost,
    )
    session.add(usage)

    await session.commit()
    return usage


async def save_debug_trace(
    session: AsyncSession,
    *,
    conversation_id: int,
    trace: DebugTrace,
) -> DebugTraceRecord:
    """
    Saves the full debug trace of one turn as JSON.

    `trace` is the Pydantic DebugTrace object the handlers filled during the
    turn. We store conversation.id on it, dump it to a plain dict, and save
    one row. Later, read it back by conversation_id to debug that turn.
    """
    trace.conversation_id = conversation_id

    record = DebugTraceRecord(
        conversation_id=conversation_id,
        intent=trace.intent or "unknown",
        # mode="json" turns nested Pydantic models into plain JSON-safe values.
        trace=trace.model_dump(mode="json"),
    )
    session.add(record)

    await session.commit()
    return record