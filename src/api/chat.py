from fastapi import APIRouter, Depends
from pydantic import BaseModel
from src.api.dependencies import get_flow_manager
from src.core.flow_manager import FlowManager

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    session_id: str


class ChatResponse(BaseModel):
    response: str


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, flow_manager: FlowManager = Depends(get_flow_manager)):
    response = flow_manager.process_message(request.message, session_id=request.session_id)
    return ChatResponse(response=response)