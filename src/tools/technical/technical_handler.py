import logging
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from src.config.setting import settings

logger = logging.getLogger(__name__)


class TechnicalCategory(str, Enum):
    TECHNICAL_USAGE    = "technical_usage"     # specs, pressure, temperature questions
    SUGGESTION         = "suggestion"           # recommend a valve for a use case
    COMPARE            = "compare"              # difference between two valves
    GENERAL_ENGINEERING = "general_engineering" # standards, terms, definitions


class ToolDecision(str, Enum):
    CATALOG_ONLY      = "catalog_only"      # search ChromaDB only
    WEB_ONLY          = "web_only"          # search web only
    BOTH              = "both"              # search both catalog + web
    LLM_THEN_CATALOG  = "llm_then_catalog"  # LLM suggests product → then catalog



class TechnicalDecision(BaseModel):
    category: TechnicalCategory = Field(
        description="The category of the technical question."
    )
    tool: ToolDecision = Field(
        description="Which tool(s) should be used to answer this question."
    )
    reasoning: str = Field(
        description="Brief explanation of why this category and tool were chosen."
    )
    query_fa: str = Field(
        description="Cleaned and formal version of the user question in Persian for search."
    )
    query_en: str = Field(
        description="Translated and formal version of the user question in English for web search."
    )


# ─────────────────────────────────────────────
# Prompt Template
# ─────────────────────────────────────────────

DECIDER_PROMPT = """
You are an expert technical assistant for industrial valves.
Your job is to analyze the user's question and decide:
1. Which category it belongs to
2. Which tool(s) should be used to answer it
3. Produce a clean formal search query in both Persian and English

## Categories:
- technical_usage: Questions about specs of a specific valve (pressure, temperature, material, size, installation, standards)
- suggestion: User wants recommendation — which valve to use for a specific application
- compare: User wants to compare two or more valves
- general_engineering: Questions about engineering terms, standards definitions, general concepts

## Tool Selection Rules:
- catalog_only: Use when question is about a specific product that likely exists in our catalog
- web_only: Use when question is about general engineering concepts, standards, or terms not product-specific
- both: Use when comparing products (need catalog data + broader web context) OR when catalog alone may not be enough
- llm_then_catalog: Use ONLY for suggestion category — LLM first decides which product fits, then we verify in catalog

## Chat History (for context):
{history}

## User Question:
{message}

Analyze carefully and return your decision.
"""

decider_prompt_template = ChatPromptTemplate.from_template(DECIDER_PROMPT)



class TechnicalHandler:
    """
    Main orchestrator for technical intent.
    Decides which tool to use and routes accordingly.
    """

    def __init__(self):
        self.llm = ChatOpenAI(
            api_key=settings.OPENAI_API_KEY,
            model="gpt-4o",
            temperature=0.0,
        )
        self.structured_llm = self.llm.with_structured_output(TechnicalDecision)
        self.decider_chain = decider_prompt_template | self.structured_llm

    def decide(self, message: str, history: list) -> TechnicalDecision:
        """
        Calls LLM decider to classify question and choose tool.
        """
        formatted_history = self._format_history(history)
        decision = self.decider_chain.invoke({
            "message": message,
            "history": formatted_history,
        })
        logger.info(
            f"TechnicalHandler: category=[{decision.category}] "
            f"tool=[{decision.tool}] reasoning=[{decision.reasoning}]"
        )
        return decision

    def _format_history(self, history: list) -> str:
        """Converts memory history list to readable string for prompt."""
        if not history:
            return "No previous conversation."
        lines = []
        for msg in history:
            role = "User" if msg["role"] == "user" else "Assistant"
            lines.append(f"{role}: {msg['content']}")
        return "\n".join(lines)



def handle_technical_query(
    message: str,
    session_id: str,
    history: list,
) -> str:
    """
    Entry point for technical intent.
    Called by flow_manager.py when intent == 'technical'.

    Steps:
    1. LLM decider → get TechnicalDecision
    2. Route to correct tool based on decision.tool
    3. Return response string

    Tools (rag_system, web_searcher) will be connected in next steps.
    """
    try:
        handler = TechnicalHandler()
        decision = handler.decide(message, history)

        logger.info(f"TechnicalHandler: Routing to [{decision.tool}] for session [{session_id}]")

        # ── Routing Logic ──────────────────────────────────────
        if decision.tool == ToolDecision.CATALOG_ONLY:
            return _route_catalog(decision, session_id)

        elif decision.tool == ToolDecision.WEB_ONLY:
            return _route_web(decision, session_id)

        elif decision.tool == ToolDecision.BOTH:
            return _route_both(decision, session_id)

        elif decision.tool == ToolDecision.LLM_THEN_CATALOG:
            return _route_llm_then_catalog(decision, message, session_id, history)

        else:
            logger.warning(f"TechnicalHandler: Unknown tool decision [{decision.tool}]")
            return "متأسفانه نتوانستم پاسخ مناسبی پیدا کنم. لطفاً سوال خود را دوباره مطرح کنید."

    except Exception as e:
        logger.error(f"TechnicalHandler: Error processing technical query: {e}", exc_info=True)
        return "مشکلی در پردازش سوال فنی به وجود آمده است."



def _route_catalog(decision: TechnicalDecision, session_id: str) -> str:
    """Routes to RAG system (ChromaDB catalog search)."""
    # TODO: connect rag_system.py in next step
    logger.info(f"TechnicalHandler: [catalog] query_fa=[{decision.query_fa}]")
    return "در حال جستجو در کاتالوگ محصولات... (در مرحله بعدی پیاده‌سازی می‌شود)"


def _route_web(decision: TechnicalDecision, session_id: str) -> str:
    """Routes to Tavily web searcher."""
    # TODO: connect web_searcher.py in next step
    logger.info(f"TechnicalHandler: [web] query_en=[{decision.query_en}]")
    return "در حال جستجو در اینترنت... (در مرحله بعدی پیاده‌سازی می‌شود)"


def _route_both(decision: TechnicalDecision, session_id: str) -> str:
    """Routes to both catalog and web search, merges results."""
    # TODO: connect both rag_system.py + web_searcher.py in next step
    logger.info(f"TechnicalHandler: [both] searching catalog + web")
    return "در حال جستجو در کاتالوگ و اینترنت... (در مرحله بعدی پیاده‌سازی می‌شود)"


def _route_llm_then_catalog(
    decision: TechnicalDecision,
    message: str,
    session_id: str,
    history: list,
) -> str:
    """
    For suggestion category:
    LLM first suggests which product fits the use case,
    then we verify and fetch details from catalog.
    """
    # TODO: implement LLM suggestion + catalog verification in next step
    logger.info(f"TechnicalHandler: [llm_then_catalog] suggestion flow started")
    return "در حال بررسی بهترین شیر برای کاربرد شما... (در مرحله بعدی پیاده‌سازی می‌شود)"