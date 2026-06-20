import logging
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from tavily import TavilyClient
from src.config.setting import settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────

TOP_K = 3  # max results from Tavily


# ─────────────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────────────

class TransformedQuery(BaseModel):
    english_query: str = Field(
        description="Formal English search query transformed from Persian user question."
    )



class WebSearchAnswer(BaseModel):
    is_relevant: bool = Field(
        description="True if search results contain relevant answer. False if nothing useful found."
    )
    answer_fa: str = Field(
        description="Final answer in Persian based on search results. Empty string if not relevant."
    )

# ─────────────────────────────────────────────
# Prompt Templates
# ─────────────────────────────────────────────

QUERY_TRANSFORM_PROMPT = """
You are a technical search expert for industrial valves.
Transform the Persian user question into a formal English search query.

## Rules:
- Keep technical terms accurate (valve types, standards, pressure ratings)
- Make query specific and searchable
- Focus on the core technical question
- Keep it concise (max 10 words)

## Persian Question:
{question}

Transform to English search query.
"""

WEB_ANSWER_PROMPT = """
You are a technical assistant for industrial valves.
A user asked a technical question and we found these web search results.
Generate a helpful Persian answer based on the results.

## User Question (Persian):
{question}

## Search Results:
{results}

## Rules:
- Answer ONLY in Persian
- Use information from the results only — never fabricate
- If results don't answer the question → set is_relevant=False
- Keep answer concise and technical
- Mention sources naturally in your answer
- If results are in English → translate relevant parts to Persian in your answer
"""

query_transform_template = ChatPromptTemplate.from_template(QUERY_TRANSFORM_PROMPT)
web_answer_template = ChatPromptTemplate.from_template(WEB_ANSWER_PROMPT)


# ─────────────────────────────────────────────
# Web Searcher Class
# ─────────────────────────────────────────────

class WebSearcher:
    """
    Handles web search pipeline:
    1. Transform query to English
    2. Search with Tavily
    3. Filter + generate Persian answer
    """

    def __init__(self):
        self.llm = ChatOpenAI(
            api_key=settings.OPENAI_API_KEY,
            model="gpt-4o-mini",
            temperature=0.0,
            max_tokens=400,
            timeout=15,
        )
        self.tavily = TavilyClient(api_key=settings.TAVILY_API_KEY)

        # Chains
        self.transform_chain = (
            query_transform_template
            | self.llm.with_structured_output(TransformedQuery)
        )
        self.answer_chain = (
            web_answer_template
            | self.llm.with_structured_output(WebSearchAnswer)
        )

    def transform_query(self, question: str) -> TransformedQuery:
        """Transforms Persian question to formal English search query."""
        result = self.transform_chain.invoke({"question": question})
        logger.info(f"WebSearcher: Query transformed → [{result.english_query}]")
        return result

    def search(self, english_query: str) -> list[dict]:
        """
        Searches web using Tavily API.
        Returns top-k results.
        """
        response = self.tavily.search(
            query=english_query,
            max_results=TOP_K,
            search_depth="advanced",
        )
        results = response.get("results", [])
        logger.info(f"WebSearcher: Tavily found [{len(results)}] results")
        return results

    def generate_answer(
        self,
        question: str,
        results: list[dict],
    ) -> WebSearchAnswer:
        """
        Filters results and generates Persian answer using GPT-4o mini.
        Combines filtering + answer generation in ONE LLM call!
        """
        # Format results for LLM
        formatted = ""
        for i, r in enumerate(results):
            formatted += f"""
Result {i + 1}:
Title: {r.get('title', '')}
URL: {r.get('url', '')}
Content: {r.get('content', '')[:600]}
---"""

        answer = self.answer_chain.invoke({
            "question": question,
            "results": formatted,
        })

        logger.info(
            f"WebSearcher: Answer generated — "
            f"relevant={answer.is_relevant} "
            
        )
        return answer


# ─────────────────────────────────────────────
# Main Entry Function
# ─────────────────────────────────────────────

def search_web(question: str) -> dict:
    """
    Main entry function called by technical_handler.py.

    Returns:
        {
            "success": bool,
            "answer": str (Persian),
            "english_query": str
        }
    """
    try:
        searcher = WebSearcher()

        # Step 1: Transform query
        transformed = searcher.transform_query(question)

        # Step 2: Search web
        results = searcher.search(transformed.english_query)

        if not results:
            logger.warning("WebSearcher: No results from Tavily")
            return {
                "success": False,
                "answer": "متأسفانه نتیجه‌ای در اینترنت پیدا نشد.",
                "english_query": transformed.english_query,
            }

        # Step 3: Filter + generate answer
        answer = searcher.generate_answer(question, results)

        if not answer.is_relevant:
            logger.warning("WebSearcher: Results not relevant to question")
            return {
                "success": False,
                "answer": "متأسفانه اطلاعات دقیقی برای این سوال پیدا نکردم.",
                "english_query": transformed.english_query,
            }

        return {
            "success": True,
            "answer": answer.answer_fa,
            "english_query": transformed.english_query,
        }

    except Exception as e:
        logger.error(f"WebSearcher: Error — {e}", exc_info=True)
        return {
            "success": False,
            "answer": "مشکلی در جستجوی اینترنتی به وجود آمده است.",
            "english_query": "",
        }