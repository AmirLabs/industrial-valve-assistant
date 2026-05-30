import logging
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from src.config.setting import settings

logger = logging.getLogger(__name__)

# Keyword bank for Persian greetings
GREETING_KEYWORDS = [
    "سلام", "درود", "روز بخیر", "روزتون بخیر", "صبح بخیر", "شب بخیر",
    "خسته نباشید", "خدا قوت", "چطوری", "خوبی", "احوال شما"
]

# Standard static onboarding response
CAPABILITIES_TEMPLATE = (
    "سلام! وقت شما بخیر. به دستیار هوشمند شرکت کنترل انرژی شهر (CEC) خوش آمدید. 🌹\n\n"
    "من اینجا هستم تا به شما در زمینه انواع شیرآلات صنعتی کمک کنم. "
    "می‌توانید در موارد زیر از من سوال بپرسید:\n"
    "🔹 **استعلام قیمت و موجودی:** (مثلاً: قیمت شیر فلکه کشویی میراب چنده؟)\n"
    "🔹 **مشخصات فنی و کاتالوگ:** (مثلاً: تفاوت شیر پروانه‌ای ویفری و فلنج‌دار چیه؟)\n"
    "🔹 **اطلاعات شرکت و گارانتی:** (مثلاً: شرایط مرجوعی کالا یا مدت گارانتی برند فاراب)\n"
    "🔹 **پشتیبانی و فروش:** (مثلاً: شماره تماس مدیر فروش یا آدرس انبار برای تحویل حضوری)\n\n"
    "چطور می‌توانم کمکتان کنم؟ لطفاً سوال خود را بفرمایید."
)

# Initialize a lightweight LLM instance for friendly chit-chat
llm = ChatOpenAI(api_key=settings.OPENAI_API_KEY, model="gpt-4o", temperature=0.5)


def handle_general_query(user_text: str) -> str:
    """
    Handles general greetings and chit-chat. 
    Uses Rule-based matching first for 0-cost, and falls back to LLM for creative onboarding.
    """
    cleaned_text = user_text.strip()
    words = cleaned_text.split()
    
    # Layer 1: Zero-cost rule matching
    is_greeting = any(kw in cleaned_text for kw in GREETING_KEYWORDS) or \
                  any(word in GREETING_KEYWORDS for word in words)

    if is_greeting:
        return CAPABILITIES_TEMPLATE
        
    # Layer 2: LLM Fallback for warm, open-ended small talk
    try:
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a warm, welcoming AI chatbot for City Energy Control (CEC), an industrial valve company. "
                       "The user is engaging in general small talk or asking who you are. "
                       "Respond politely and briefly in Persian, then explicitly guide them to ask about "
                       "industrial valves, prices, technical specifications, or warranties to keep them engaged."),
            ("human", "{query}")
        ])
        
        chain = prompt | llm | StrOutputParser()
        return chain.invoke({"query": cleaned_text})
        
    except Exception as e:
        logger.error(f"General tool LLM fallback failed: {e}")
        # Secure fallback if OpenAI API fails
        return CAPABILITIES_TEMPLATE