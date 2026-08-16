import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from langchain_community.callbacks import get_openai_callback

from src.core.router import IntentRouter
from src.tools.faq.retriever import get_chat_response
from src.tools.general.handler import handle_general_query
from src.tools.pricing.price_handler import handle_price_query
from src.tools.technical.technical_handler import handle_technical_query
from src.status.memory import MemoryManager
from src.status.slot_manager import SlotManager
from src.status.technical_context import TechnicalContext
from src.database.debug_trace import (
    DebugTrace,
    GeneralTrace,
    FaqTrace,
    TechnicalTrace,
    PricingTrace,
)

logger = logging.getLogger(__name__)


@dataclass
class ProcessResult:
    """
    Everything the API layer needs to both answer the user AND log the turn.
    response       -> the text shown to the user
    intent         -> "general" | "faq" | "pricing" | "technical" | "error"
    execution_time -> total time spent in process_message, in seconds
    router_time    -> time spent just in router.route_message (None if the pricing
                       slot-filling shortcut skipped the router entirely)
    metadata       -> the full per-step timing breakdown, saved as-is into rag_metadata
    error          -> text of the exception, if one happened
    token_usages   -> one dict per model call, e.g.
                       {"step": "router", "model_name": "gpt-4o-mini",
                        "prompt_tokens": 120, "completion_tokens": 4}
                       The API layer loops over this and saves one token_usage row each.
    debug_trace    -> the full DebugTrace object (nested per-step details),
                       saved as JSON into the debug_traces table for debugging.
    """
    response: str
    intent: str
    execution_time: float
    router_time: Optional[float] = None
    metadata: Dict[str, float] = field(default_factory=dict)
    error: Optional[str] = None
    token_usages: List[Dict] = field(default_factory=list)
    debug_trace: Optional[DebugTrace] = None

class FlowManager:
    def __init__(self):
        self.router = IntentRouter()
        self.memory = MemoryManager(window_size=8)
        self.slot_managers: Dict[str, SlotManager] = {}              # one SlotManager per session
        self.technical_contexts: Dict[str, TechnicalContext] = {}    # one TechnicalContext per session

    def _get_slot(self, session_id: str) -> SlotManager:
        """Returns existing SlotManager for session or creates a new one."""
        if session_id not in self.slot_managers:
            self.slot_managers[session_id] = SlotManager(session_id)
        return self.slot_managers[session_id]

    def _get_technical_context(self, session_id: str) -> TechnicalContext:
        """Returns existing TechnicalContext for session or creates a new one."""
        if session_id not in self.technical_contexts:
            self.technical_contexts[session_id] = TechnicalContext(session_id)
        return self.technical_contexts[session_id]

    def _has_pending_price_session(self, session_id: str) -> bool:
        """Checks if user is already inside a pricing flow."""
        slot = self._get_slot(session_id)
        return slot.is_active

    def process_message(self, user_message: str, session_id: str) -> ProcessResult:
        t_start = time.perf_counter()
        timings = {}
        logger.info(f"FlowManager: Message received [{session_id}]")

        # Collects step-by-step debug details for this turn. Handlers write
        # into their matching sub-trace; we save the whole thing as JSON later.
        # Built BEFORE the try so the except block can always return it - even
        # if the turn dies on the very first line.
        trace = DebugTrace(session_id=session_id)

        try:
            cleaned_message = user_message.strip()
            if not cleaned_message:
                empty_reply = "لطفاً پیام خود را به صورت متنی بنویسید."
                return ProcessResult(
                    response=empty_reply,
                    intent="general",
                    execution_time=time.perf_counter() - t_start,
                )

            t0 = time.perf_counter()
            self.memory.add_message(session_id, "user", cleaned_message)
            history = self.memory.get_history(session_id)
            timings["memory_read"] = time.perf_counter() - t0

            # One dict per model call. The API layer turns each into a token_usage row.
            token_usages: List[Dict] = []

            def _record(cb, step: str, model_name: str) -> None:
                """Add one token_usages entry from a get_openai_callback box.
                Skips steps that made no model call (e.g. a greeting), so we never
                save empty 0-token rows."""
                if cb.total_tokens == 0:
                    return
                token_usages.append({
                    "step": step,
                    "model_name": model_name,
                    "prompt_tokens": cb.prompt_tokens,
                    "completion_tokens": cb.completion_tokens,
                })

            slot = self._get_slot(session_id)

            if self._has_pending_price_session(session_id):
                logger.info(f"FlowManager: Continuing pending price session [{session_id}]")
                t0 = time.perf_counter()
                trace.pricing = PricingTrace()
                with get_openai_callback() as cb:
                    response = handle_price_query(cleaned_message, slot=slot, trace=trace.pricing)
                _record(cb, "pricing", "gpt-4o")
                timings["handle_price_query (pending session)"] = time.perf_counter() - t0
                # Router was skipped (slot-filling shortcut), but this is still a pricing turn.
                detected_intent = "pricing"

            else:
                t0 = time.perf_counter()
                with get_openai_callback() as cb:
                    intent_analysis = self.router.route_message(cleaned_message)
                _record(cb, "router", "gpt-4o-mini")
                detected_intent = intent_analysis.intent
                trace.router.detected_intent = detected_intent
                timings["router.route_message"] = time.perf_counter() - t0

                logger.info(f"FlowManager: Processing message with intent [{detected_intent}]")

                if detected_intent == "general":
                    t0 = time.perf_counter()
                    trace.general = GeneralTrace()
                    with get_openai_callback() as cb:
                        response = handle_general_query(cleaned_message, history=history, trace=trace.general)
                    _record(cb, "general", "gpt-4o")
                    timings["handle_general_query"] = time.perf_counter() - t0

                elif detected_intent == "faq":
                    t0 = time.perf_counter()
                    trace.faq = FaqTrace()
                    with get_openai_callback() as cb:
                        response = get_chat_response(cleaned_message, history=history, trace=trace.faq)
                    # faq mixes gpt-4o-mini (query cleanup) + gpt-4o (answer); we label the
                    # main answer model. Cost is close, not exact - see Option A.
                    _record(cb, "faq", "gpt-4o")
                    timings["get_chat_response (faq/RAG)"] = time.perf_counter() - t0
                    if not response:
                        response = "پاسخی برای این سوال پیدا نشد. چطور می‌توانم کمکتان کنم؟"

                elif detected_intent == "pricing":
                    t0 = time.perf_counter()
                    trace.pricing = PricingTrace()
                    with get_openai_callback() as cb:
                        response = handle_price_query(cleaned_message, slot=slot, trace=trace.pricing)
                    _record(cb, "pricing", "gpt-4o")
                    timings["handle_price_query"] = time.perf_counter() - t0

                elif detected_intent == "technical":
                    technical_context = self._get_technical_context(session_id)
                    t0 = time.perf_counter()
                    trace.technical = TechnicalTrace()
                    with get_openai_callback() as cb:
                        response = handle_technical_query(
                            cleaned_message,
                            history=history,
                            context=technical_context,
                            trace=trace.technical,
                        )
                    # technical also mixes models; label the main model (Option A).
                    _record(cb, "technical", "gpt-4o")
                    timings["handle_technical_query"] = time.perf_counter() - t0

                else:
                    logger.warning(f"FlowManager: Intent [{detected_intent}] not implemented yet.")
                    response = "پاسخ‌گویی به این نوع درخواست هنوز راه‌اندازی نشده است."

            t0 = time.perf_counter()
            self.memory.add_message(session_id, "assistant", response)
            timings["memory_write"] = time.perf_counter() - t0

            total = time.perf_counter() - t_start
            timings["TOTAL"] = total

            # Fill the top-level trace fields now that the turn is done.
            trace.intent = detected_intent
            trace.execution_time = total

            # Pretty timing breakdown in logs - this is the line you care about
            breakdown = " | ".join(f"{k}: {v:.2f}s" for k, v in timings.items())
            logger.info(f"FlowManager TIMING [{session_id}] -> {breakdown}")

            return ProcessResult(
                response=response,
                intent=detected_intent,
                execution_time=total,
                router_time=timings.get("router.route_message"),
                metadata=timings,
                token_usages=token_usages,
                debug_trace=trace,
            )

        except Exception as e:
            total = time.perf_counter() - t_start
            logger.error(f"Critical error in FlowManager after {total:.2f}s: {e}", exc_info=True)
            return ProcessResult(
                response="مشکلی در پردازش پیام به وجود آمده است.",
                intent="error",
                execution_time=total,
                error=str(e),
            )