import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from langchain_community.callbacks import get_openai_callback

from src.core.router import IntentRouter, PendingAction
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

CANCEL_MESSAGE = "باشه، استعلام قیمت رو لغو کردم. هر وقت کاری داشتید در خدمتم."

GIVE_UP_MESSAGE = (
    "فعلاً استعلام قیمت رو نگه می‌دارم. "
    "هر وقت خواستید ادامه بدیم، فقط بگید."
)


def _build_return_line(slot: SlotManager, about_current_options: bool) -> str:
    """
    Builds the sentence that brings the user back to the waiting question,
    after we answered something else for them.
    """
    if about_current_options and slot.options:
        choices = " یا ".join(str(o) for o in slot.options)
        return f"حالا که بیشتر آشنا شدید، کدوم رو ترجیح می‌دید؟ {choices}"
    return f"برگردیم به استعلام قیمت؟\n{slot.last_question}"


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

    def _handle_pending_turn(
        self,
        *,
        decision,
        message: str,
        slot: SlotManager,
        history: list,
        session_id: str,
        trace: DebugTrace,
        record,
        timings: Dict[str, float],
    ) -> tuple:
        """
        Runs one turn that arrived while a price quote was waiting for an answer.

        Returns (intent, response). The four paths are:
          continue -> feed the answer into the slot, as before
          cancel   -> drop the quote
          pricing  -> the user wants a different product, start over
          other    -> answer their question, then ask ours again
        """
        action = decision.action

        # --- The user gave up ---
        if action is PendingAction.CANCEL:
            slot.reset()
            trace.pricing.slot_state = slot.state.value
            return "pricing", CANCEL_MESSAGE

        # --- The user answered us ---
        if action is PendingAction.CONTINUE:
            answer_text = self._pick_answer_text(decision, message, slot)
            t0 = time.perf_counter()
            with get_openai_callback() as cb:
                response = handle_price_query(answer_text, slot=slot, trace=trace.pricing)
            record(cb, "pricing", "gpt-4o")
            timings["handle_price_query (pending session)"] = time.perf_counter() - t0
            return "pricing", response

        # --- The user asks about a different product: drop the old quote, start fresh ---
        if action is PendingAction.PRICING:
            slot.reset()
            t0 = time.perf_counter()
            with get_openai_callback() as cb:
                response = handle_price_query(message, slot=slot, trace=trace.pricing)
            record(cb, "pricing", "gpt-4o")
            timings["handle_price_query (new product)"] = time.perf_counter() - t0
            return "pricing", response

        # --- The user stepped away to ask something else ---
        slot.pause()
        trace.pricing.detour_intent = action.value
        trace.pricing.detour_count = slot.detour_count

        question = decision.rewritten_question or message
        logger.info(f"FlowManager: Detour to [{action.value}] with query [{question}]")

        answer = self._answer_detour(
            action=action,
            question=question,
            history=history,
            session_id=session_id,
            trace=trace,
            record=record,
            timings=timings,
        )

        # Too many detours - let the quote go instead of nagging the user.
        if slot.detour_limit_reached():
            slot.reset()
            trace.pricing.slot_state = slot.state.value
            return action.value, f"{answer}\n\n{GIVE_UP_MESSAGE}"

        slot.resume()
        trace.pricing.slot_state = slot.state.value
        return action.value, f"{answer}\n\n{_build_return_line(slot, decision.about_current_options)}"

    # staticmethod because this only reads its own arguments - no self, so it
    # can never touch or break the manager's state.
    @staticmethod
    def _pick_answer_text(decision, message: str, slot: SlotManager) -> str:
        """
        Chooses what to feed the price handler when the user answered us.

        We prefer the value the router cleaned up, but only when it really is one
        of the choices we offered - the model must never invent a brand or size.
        """
        value = decision.normalized_value
        if not value:
            return message

        # Yes/no answers are handled inside price_handler, keep the raw words.
        if slot.waiting_for == "product_confirmation":
            return message

        if slot.options and value not in slot.options:
            logger.warning(
                f"FlowManager: router returned '{value}' which is not in "
                f"{slot.options}; using the raw message instead"
            )
            return message

        return value

    def _answer_detour(
        self,
        *,
        action,
        question: str,
        history: list,
        session_id: str,
        trace: DebugTrace,
        record,
        timings: Dict[str, float],
    ) -> str:
        """Answers the off-topic question the user asked in the middle of a quote."""
        t0 = time.perf_counter()

        if action is PendingAction.TECHNICAL:
            trace.technical = TechnicalTrace()
            with get_openai_callback() as cb:
                answer = handle_technical_query(
                    question,
                    history=history,
                    context=self._get_technical_context(session_id),
                    trace=trace.technical,
                )
            record(cb, "technical", "gpt-4o")

        elif action is PendingAction.FAQ:
            trace.faq = FaqTrace()
            with get_openai_callback() as cb:
                answer = get_chat_response(question, history=history, trace=trace.faq)
            record(cb, "faq", "gpt-4o")

        else:
            trace.general = GeneralTrace()
            with get_openai_callback() as cb:
                answer = handle_general_query(question, history=history, trace=trace.general)
            record(cb, "general", "gpt-4o")

        timings[f"detour ({action.value})"] = time.perf_counter() - t0
        return answer

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

            if self._has_pending_price_session(session_id) and slot.last_question:
                # We asked the user something and this is their reply. It may be the
                # answer, a change of mind, or a different question - so we ask the
                # router instead of pushing every message straight into the slot.
                logger.info(f"FlowManager: Continuing pending price session [{session_id}]")
                t0 = time.perf_counter()
                trace.pricing = PricingTrace()

                with get_openai_callback() as cb:
                    decision = self.router.route_pending(
                        cleaned_message,
                        question_text=slot.last_question,
                        options=slot.options,
                    )
                _record(cb, "router_pending", "gpt-4o-mini")
                timings["router.route_pending"] = time.perf_counter() - t0

                trace.pricing.pending_action = decision.action.value
                logger.info(f"FlowManager: Pending decision [{decision.action.value}]")

                detected_intent, response = self._handle_pending_turn(
                    decision=decision,
                    message=cleaned_message,
                    slot=slot,
                    history=history,
                    session_id=session_id,
                    trace=trace,
                    record=_record,
                    timings=timings,
                )

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

            # Keep whatever the handlers managed to fill before the crash - that
            # partial trace is exactly what tells us how far the turn got.
            trace.error = str(e)
            trace.intent = "error"
            trace.execution_time = total

            return ProcessResult(
                response="مشکلی در پردازش پیام به وجود آمده است.",
                intent="error",
                execution_time=total,
                error=str(e),
                debug_trace=trace,
            )