import logging
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from src.config.setting import settings

logger = logging.getLogger(__name__)

GREETING_KEYWORDS = [
    "سلام", "درود", "روز بخیر", "روزتون بخیر", "صبح بخیر", "شب بخیر",
    "خسته نباشید", "خدا قوت", "چطوری", "خوبی", "احوال شما"
]

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

llm = ChatOpenAI(api_key=settings.OPENAI_API_KEY, model="gpt-4o", temperature=0.5)


def handle_general_query(user_text: str, history: list = None, trace=None) -> str:
    cleaned_text = user_text.strip()
    words = cleaned_text.split()

    is_greeting = any(kw in cleaned_text for kw in GREETING_KEYWORDS) or \
                  any(word in GREETING_KEYWORDS for word in words)

    if trace:
        trace.is_greeting = is_greeting

    if is_greeting:
        # Fixed template - no model call happened.
        if trace:
            trace.used_llm = False
        return CAPABILITIES_TEMPLATE

    try:
        messages = [
            ("system",
             "You are a warm, welcoming AI chatbot for City Energy Control (CEC), an industrial valve company. "
             "The user is engaging in general small talk or asking who you are. "
             "Respond politely and briefly in Persian, then explicitly guide them to ask about "
             "industrial valves, prices, technical specifications, or warranties to keep them engaged.")
        ]

        if history:
            for msg in history[:-1]:
                messages.append((msg["role"], msg["content"]))

        messages.append(("human", "{query}"))

        prompt = ChatPromptTemplate.from_messages(messages)
        chain = prompt | llm | StrOutputParser()
        if trace:
            trace.used_llm = True
        return chain.invoke({"query": cleaned_text})

    except Exception as e:
        logger.error(f"General tool LLM fallback failed: {e}")
        if trace:
            trace.used_llm = False
        return CAPABILITIES_TEMPLATE