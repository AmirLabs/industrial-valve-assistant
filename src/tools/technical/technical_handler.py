import logging
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from src.config.setting import settings
from src.tools.technical.rag_system import search_catalog, verify_with_crag
from src.tools.technical.web_searcher import search_web
from src.tools.technical.asset_manager import build_fallback_message
from src.data.application_products import products_list_with_application
from src.status.technical_context import TechnicalContext
from src.prompts.technical import DECIDER_PROMPT,SUGGESTION_PROMPT,FINAL_ANSWER_PROMPT
from src.tools.technical.llm_knowledge import get_llm_knowledge_answer
logger = logging.getLogger(__name__)

class TechnicalCategory(str, Enum):
    TECHNICAL_USAGE      = "technical_usage"
    SUGGESTION           = "suggestion"
    COMPARE               = "compare"
    GENERAL_ENGINEERING   = "general_engineering"



class TechnicalDecision(BaseModel):
    category: TechnicalCategory = Field(
        description="The category of the technical question."
    )
    query_fa: str = Field(
        description="Cleaned and formal version of the user question in Persian for search. "
                    "If the question refers to a previous product (e.g. 'همین شیر'), resolve it "
                    "using the remembered product context and write the full explicit query."
    )
    brand: Optional[str] = Field(
        None,
        description="Brand mentioned by the user, or inherited from remembered context if the "
                    "question refers to a previous product. Null if not known."
    )



decider_prompt_template = ChatPromptTemplate.from_template(DECIDER_PROMPT)
suggestion_prompt_template = ChatPromptTemplate.from_template(SUGGESTION_PROMPT)
final_answer_prompt_template = ChatPromptTemplate.from_template(FINAL_ANSWER_PROMPT)


class SuggestionQuery(BaseModel):
    search_query_fa: str = Field(
        description="Persian search query combining suggested product type and/or brand, for catalog search."
    )


class FinalAnswer(BaseModel):
    answer_fa: str = Field(description="Final Persian answer for the user.")


def _format_products_catalog() -> str:
    """Formats products_list_with_application into readable text for the LLM prompt."""
    lines = []
    for item in products_list_with_application:
        name = item.get("product_name", "")
        application = item.get("application", "")
        lines.append(f"- {name} ← {application}")
    return "\n".join(lines)


def _format_remembered_product(context: Optional[TechnicalContext]) -> str:
    """Formats the remembered product for the decider prompt."""
    if not context or not context.last_product:
        return "No remembered product — this is a fresh question."
    p = context.last_product
    return (
        f"product_name: {p.get('product_name')}\n"
        f"brand: {p.get('brand')}\n"
        f"product_type: {p.get('product_type')}\n"
        f"pressure: {p.get('pressure')}\n"
        f"max_temp: {p.get('max_temp')}"
    )


# ─────────────────────────────────────────────
# Technical Handler
# ─────────────────────────────────────────────

class TechnicalHandler:
    """
    Main orchestrator for technical intent.
    Decides category and routes accordingly.
    Stateless — all session state lives in TechnicalContext, passed in by FlowManager.
    """

    def __init__(self):
        self.llm = ChatOpenAI(
            api_key=settings.OPENAI_API_KEY,
            model="gpt-4o",
            temperature=0.0,
        )
        self.mini_llm = ChatOpenAI(
            api_key=settings.OPENAI_API_KEY,
            model="gpt-4o-mini",
            temperature=0.0,
        )

        self.structured_llm = self.llm.with_structured_output(TechnicalDecision)
        self.decider_chain = decider_prompt_template | self.structured_llm

        self.suggestion_chain = (
            suggestion_prompt_template
            | self.mini_llm.with_structured_output(SuggestionQuery)
        )

        self.final_answer_chain = (
            final_answer_prompt_template
            | self.mini_llm.with_structured_output(FinalAnswer)
        )

    def decide(
        self,
        message: str,
        history: list,
        context: Optional[TechnicalContext],
    ) -> TechnicalDecision:
        """Calls LLM decider to classify question and choose search query."""
        formatted_history = self._format_history(history)
        remembered_product = _format_remembered_product(context)

        decision = self.decider_chain.invoke({
            "message": message,
            "history": formatted_history,
            "remembered_product": remembered_product,
        })
        logger.info(
            f"TechnicalHandler: category=[{decision.category}] ")
        return decision

    def suggest_product(self, message: str, history: list) -> SuggestionQuery:
        """For suggestion category: asks LLM which product fits the use case, from our real catalog."""
        formatted_history = self._format_history(history)
        products_catalog = _format_products_catalog()
        result = self.suggestion_chain.invoke({
            "message": message,
            "history": formatted_history,
            "products_catalog": products_catalog,
        })
        logger.info(f"TechnicalHandler: suggestion search_query_fa=[{result.search_query_fa}]")
        return result

    def write_final_answer(self, question: str, content: str) -> str:
        """Turns raw catalog content into a clean Persian answer."""
        result = self.final_answer_chain.invoke({
            "question": question,
            "content": content,
        })
        return result.answer_fa

    def _format_history(self, history: list) -> str:
        """Converts memory history list to readable string for prompt."""
        if not history:
            return "No previous conversation."
        lines = []
        for msg in history:
            role = "User" if msg["role"] == "user" else "Assistant"
            lines.append(f"{role}: {msg['content']}")
        return "\n".join(lines)


# ─────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────

def handle_technical_query(
    message: str,
    history: list,
    context: TechnicalContext,
    trace=None,
) -> str:
    """
    Entry point for technical intent.
    Called by flow_manager.py when intent == 'technical'.

    `context` is owned and persisted by FlowManager (same pattern as SlotManager for pricing).
    """
    try:
        handler = TechnicalHandler()
        decision = handler.decide(message, history, context)

        if trace:
            trace.category = str(decision.category.value)
            trace.query_fa = decision.query_fa
            trace.brand = decision.brand

        logger.info(f"TechnicalHandler: Routing category=[{decision.category}]")

        if decision.category == TechnicalCategory.TECHNICAL_USAGE:
            return _route_technical_usage(handler, decision, context, trace=trace)

        elif decision.category == TechnicalCategory.SUGGESTION:
            return _route_suggestion(handler, decision, message, history, context, trace=trace)

        elif decision.category == TechnicalCategory.COMPARE:
            return _route_compare(handler, decision, context, trace=trace)

        elif decision.category == TechnicalCategory.GENERAL_ENGINEERING:
            return _route_general_engineering(decision, trace=trace)

        else:
            logger.warning(f"TechnicalHandler: Unknown category [{decision.category}]")
            return "متأسفانه نتوانستم پاسخ مناسبی پیدا کنم. لطفاً سوال خود را دوباره مطرح کنید."

    except Exception as e:
        logger.error(f"TechnicalHandler: Error processing technical query: {e}", exc_info=True)
        return "مشکلی در پردازش سوال فنی به وجود آمده است."


# ─────────────────────────────────────────────
# Category Routers
# ─────────────────────────────────────────────

def _trace_search(trace, results) -> None:
    """Records catalog search results into the trace (top score / product / count)."""
    if not trace:
        return
    trace.results_count = len(results)
    if results:
        top = results[0]
        trace.top_score = top.score
        trace.top_product = top.metadata.get("product_name")


def _trace_crag(trace, crag) -> None:
    """Records the CRAG verification decision into the trace."""
    if not trace:
        return
    trace.crag_is_relevant = crag.is_relevant
    trace.crag_best_index = crag.best_result_index


def _route_technical_usage(
    handler: TechnicalHandler,
    decision: TechnicalDecision,
    context: TechnicalContext,
    trace=None,
) -> str:
    """technical_usage → catalog only → fallback to asset_manager link if not found."""
    logger.info(f"TechnicalHandler: [technical_usage] query_fa=[{decision.query_fa}]")

    results = search_catalog(decision.query_fa, brand=decision.brand)
    _trace_search(trace, results)
    if not results:
        return build_fallback_message(decision.brand)

    crag = verify_with_crag(decision.query_fa, results)
    _trace_crag(trace, crag)
    if not crag.is_relevant or crag.best_result_index is None:
        return build_fallback_message(decision.brand)

    best = results[crag.best_result_index]
    context.remember_product(best.metadata)
    return handler.write_final_answer(decision.query_fa, best.content)


def _route_suggestion(
    handler: TechnicalHandler,
    decision: TechnicalDecision,
    message: str,
    history: list,
    context: TechnicalContext,
    trace=None,
) -> str:
    """suggestion → LLM suggests product type → then catalog search to verify."""
    logger.info("TechnicalHandler: [suggestion] asking LLM for product suggestion")

    suggestion = handler.suggest_product(message, history)
    results = search_catalog(suggestion.search_query_fa)
    _trace_search(trace, results)

    if not results:
        return build_fallback_message(decision.brand)

    crag = verify_with_crag(decision.query_fa, results)
    _trace_crag(trace, crag)
    if not crag.is_relevant or crag.best_result_index is None:
        return build_fallback_message(decision.brand)

    best = results[crag.best_result_index]
    context.remember_product(best.metadata)
    return handler.write_final_answer(decision.query_fa, best.content)


def _route_compare(
    handler: TechnicalHandler,
    decision: TechnicalDecision,
    context: TechnicalContext,
    trace=None,
) -> str:
    """compare → catalog first, fallback to web search, then asset_manager link if both fail."""
    logger.info(f"TechnicalHandler: [compare] query_fa=[{decision.query_fa}]")

    results = search_catalog(decision.query_fa, brand=decision.brand)
    _trace_search(trace, results)
    if results:
        crag = verify_with_crag(decision.query_fa, results)
        _trace_crag(trace, crag)
        if crag.is_relevant and crag.best_result_index is not None:
            best = results[crag.best_result_index]
            context.remember_product(best.metadata)
            return handler.write_final_answer(decision.query_fa, best.content)

    logger.info("TechnicalHandler: [compare] catalog not sufficient, falling back to web search")
    if trace:
        trace.used_web_search = True
    web_result = search_web(decision.query_fa)

    if web_result["success"]:
        return web_result["answer"]

    logger.info("TechnicalHandler: [compare] web search also failed, falling back to catalog link")
    return build_fallback_message(decision.brand)


def _route_general_engineering(decision: TechnicalDecision, trace=None) -> str:
    logger.info(f"TechnicalHandler: [general_engineering] query_fa=[{decision.query_fa}]")

    llm_result = get_llm_knowledge_answer(decision.query_fa)
    if llm_result.is_confident and llm_result.answer_fa:
        return llm_result.answer_fa

    logger.info("TechnicalHandler: LLM not confident, falling back to web search")
    if trace:
        trace.used_web_search = True
    web_result = search_web(decision.query_fa)

    if web_result["success"]:
        return web_result["answer"]

    return build_fallback_message(decision.brand)