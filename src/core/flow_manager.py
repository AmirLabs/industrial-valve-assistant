import logging
from src.core.router import IntentRouter
from src.tools.faq.retriever import get_chat_response
from src.tools.general.handler import handle_general_query

logger = logging.getLogger(__name__)

class FlowManager:
    def __init__(self):
        self.router = IntentRouter()

    def process_message(self, user_message: str) -> str:
        """
        Orchestrates the user message by detecting intent and routing 
        to the appropriate stateless tool (FAQ or General).
        """
        try:

            cleaned_message = user_message.strip()
            if not cleaned_message:
                return "لطفاً پیام خود را به صورت متنی بنویسید."

            intent_analysis = self.router.route_message(cleaned_message)
            detected_intent = intent_analysis.intent  
            
            logger.info(f"FlowManager: Processing message with intent [{detected_intent}]")
    
            if detected_intent == "general":
                response = handle_general_query(cleaned_message)
                return response

            elif detected_intent == "faq":
                response = get_chat_response(cleaned_message)
                if not response:
                    return "پاسخی برای این سوال در بخش سوالات متداول پیدا نشد. چطور می‌توانم در زمینه شیرآلات صنعتی کمکتان کنم؟"
                return response

            else:
                logger.warning(f"FlowManager: Intent [{detected_intent}] is valid but not implemented yet.")
                return "پاسخ‌گویی به این نوع درخواست هنوز راه‌اندازی نشده است."

        except Exception as e:
            logger.error(f"Critical error in FlowManager orchestration: {e}", exc_info=True)
            return "مشکلی در پردازش پیام به وجود آمده است. لطفاً کمی بعد دوباره تلاش کنید."