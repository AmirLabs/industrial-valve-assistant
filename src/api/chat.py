from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_flow_manager, get_db_session
from src.core.flow_manager import FlowManager
from src.database.conversation_repository import (
    save_conversation_turn,
    save_token_usage,
    save_debug_trace,
)

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    session_id: str


class ChatResponse(BaseModel):
    response: str


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    flow_manager: FlowManager = Depends(get_flow_manager),
    db_session: AsyncSession = Depends(get_db_session),
):
    # process_message now catches its own errors and reports them inside result.error,
    # so we don't need a try/except here anymore - it always returns a ProcessResult.
    result = flow_manager.process_message(request.message, session_id=request.session_id)

    conversation = await save_conversation_turn(
        db_session,
        session_id=request.session_id,
        user_message=request.message,
        assistant_message=result.response,
        intent=result.intent,
        execution_time=result.execution_time,
        router_time=result.router_time,
        rag_metadata=result.metadata or None,
        error=result.error,
    )

    # One row per model call in this turn (router, faq, pricing, ...).
    # save_token_usage looks up the price and fills the cost columns for us.
    for usage in result.token_usages:
        await save_token_usage(
            db_session,
            conversation_id=conversation.id,
            step=usage["step"],
            model_name=usage["model_name"],
            prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
        )

    # Full step-by-step debug trace of this turn, saved as JSON.
    # Read it back by conversation_id when an answer looks wrong.
    if result.debug_trace is not None:
        await save_debug_trace(
            db_session,
            conversation_id=conversation.id,
            trace=result.debug_trace,
        )

    return ChatResponse(response=result.response)