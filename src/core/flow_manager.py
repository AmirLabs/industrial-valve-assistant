import logging
from src.core.router import IntentRouter
from src.tools.faq.retriever import get_chat_response
from src.tools.general.handler import handle_general_query
from src.states.memory import MemoryManager

logger = logging.getLogger(__name__)

class FlowManager:
    def __init__(self):
        self.router = IntentRouter()
        self.memory = MemoryManager(window_size=8)

    def process_message(self, user_message: str, session_id: str) -> str:
        try:
            cleaned_message = user_message.strip()
            if not cleaned_message:
                return "لطفاً پیام خود را به صورت متنی بنویسید."

            #save the message
            self.memory.add_message(session_id, "user", cleaned_message)
            
            #get history for using tools
            history = self.memory.get_history(session_id)

            intent_analysis = self.router.route_message(cleaned_message)
            detected_intent = intent_analysis.intent

            logger.info(f"FlowManager: Processing message with intent [{detected_intent}]")

            if detected_intent == "general":
                response = handle_general_query(cleaned_message, history=history)

            elif detected_intent == "faq":
                response = get_chat_response(cleaned_message, history=history)
                if not response:
                    response = "پاسخی برای این سوال پیدا نشد. چطور می‌توانم کمکتان کنم؟"

            else:
                logger.warning(f"FlowManager: Intent [{detected_intent}] not implemented yet.")
                response = "پاسخ‌گویی به این نوع درخواست هنوز راه‌اندازی نشده است."

            # ذخیره جواب assistant
            self.memory.add_message(session_id, "assistant", response)
            return response

        except Exception as e:
            logger.error(f"Critical error in FlowManager: {e}", exc_info=True)
            return "مشکلی در پردازش پیام به وجود آمده است."