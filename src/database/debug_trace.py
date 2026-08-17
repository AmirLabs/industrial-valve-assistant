from typing import Optional
from pydantic import BaseModel, Field


class RouterTrace(BaseModel):
    """The intent router step."""
    detected_intent: Optional[str] = None


class GeneralTrace(BaseModel):
    """The general (small talk) step."""
    is_greeting: Optional[bool] = None
    used_llm: Optional[bool] = None          # False when we returned the fixed greeting template


class FaqTrace(BaseModel):
    """The FAQ / RAG step (retriever.py)."""
    raw_similarity: Optional[float] = None
    normalized_query: Optional[str] = None
    # "fast_path" | "soft_match" | "llm_fallback"
    path: Optional[str] = None
    matched_answer_preview: Optional[str] = None


class TechnicalTrace(BaseModel):
    """The technical step (technical_handler.py + rag_system.py)."""
    # "technical_usage" | "suggestion" | "compare" | "general_engineering"
    category: Optional[str] = None
    query_fa: Optional[str] = None
    brand: Optional[str] = None
    results_count: Optional[int] = None
    top_score: Optional[float] = None
    top_product: Optional[str] = None
    crag_is_relevant: Optional[bool] = None
    crag_best_index: Optional[int] = None
    used_web_search: Optional[bool] = None


class PricingTrace(BaseModel):
    """The pricing step (price_handler.py)."""
    # The extracted entities, e.g. {"product_name": "کشویی", "inch": "2", ...}
    entities: Optional[dict] = None
    # "found" | "ask_user" | "wrong_size" | "suggest_product" | "not_found" | "give_up"
    slot_status: Optional[str] = None
    waiting_for: Optional[str] = None
    options: Optional[list] = None

    # --- Filled only when the message arrived while we waited for an answer ---
    # "continue" | "cancel" | "pricing" | "technical" | "faq" | "general"
    pending_action: Optional[str] = None
    # Where the user went when they stepped away from the quote.
    detour_intent: Optional[str] = None
    # How many times they stepped away so far in this quote.
    detour_count: Optional[int] = None
    # Slot state at the end of the turn: "inactive" | "active" | "paused"
    slot_state: Optional[str] = None


class DebugTrace(BaseModel):
    """The full trace of one chat turn. Saved as JSON in debug_traces.trace."""
    session_id: str
    conversation_id: Optional[int] = None
    intent: Optional[str] = None
    execution_time: Optional[float] = None
    error: Optional[str] = None

    # Only the step(s) that ran get filled; the others stay None.
    router: RouterTrace = Field(default_factory=RouterTrace)
    general: Optional[GeneralTrace] = None
    faq: Optional[FaqTrace] = None
    technical: Optional[TechnicalTrace] = None
    pricing: Optional[PricingTrace] = None
