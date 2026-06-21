import logging
from typing import Dict
from src.core.router import IntentRouter
from src.tools.faq.retriever import get_chat_response
from src.tools.general.handler import handle_general_query
from src.tools.pricing.price_handler import handle_price_query
from src.tools.technical.technical_handler import handle_technical_query
from src.status.memory import MemoryManager
from src.status.slot_manager import SlotManager
from src.status.technical_context import TechnicalContext

logger = logging.getLogger(__name__)


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

    def process_message(self, user_message: str, session_id: str) -> str:
        try:
            cleaned_message = user_message.strip()
            if not cleaned_message:
                return "لطفاً پیام خود را به صورت متنی بنویسید."

            self.memory.add_message(session_id, "user", cleaned_message)
            history = self.memory.get_history(session_id)
            slot = self._get_slot(session_id)

            if self._has_pending_price_session(session_id):
                logger.info(f"FlowManager: Continuing pending price session [{session_id}]")
                response = handle_price_query(cleaned_message, slot=slot)

            else:
                intent_analysis = self.router.route_message(cleaned_message)
                detected_intent = intent_analysis.intent

                logger.info(f"FlowManager: Processing message with intent [{detected_intent}]")

                if detected_intent == "general":
                    response = handle_general_query(cleaned_message, history=history)

                elif detected_intent == "faq":
                    response = get_chat_response(cleaned_message, history=history)
                    if not response:
                        response = "پاسخی برای این سوال پیدا نشد. چطور می‌توانم کمکتان کنم؟"

                elif detected_intent == "pricing":
                    response = handle_price_query(cleaned_message, slot=slot)

                elif detected_intent == "technical":
                    technical_context = self._get_technical_context(session_id)
                    response = handle_technical_query(
                        cleaned_message,
                        history=history,
                        context=technical_context,
                    )

                else:
                    logger.warning(f"FlowManager: Intent [{detected_intent}] not implemented yet.")
                    response = "پاسخ‌گویی به این نوع درخواست هنوز راه‌اندازی نشده است."

            self.memory.add_message(session_id, "assistant", response)
            return response

        except Exception as e:
            logger.error(f"Critical error in FlowManager: {e}", exc_info=True)
            return "مشکلی در پردازش پیام به وجود آمده است."