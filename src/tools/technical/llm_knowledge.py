import logging
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from src.config.setting import settings

logger = logging.getLogger(__name__)

LLM_KNOWLEDGE_PROMPT = """
You are an expert engineer for industrial valves.
Answer the user's question using your own general engineering knowledge.

## Rules:
- Only answer if this is GENERAL, STABLE engineering knowledge
  (valve types, standards, common definitions, general comparisons).
- If the question needs a SPECIFIC BRAND, MODEL, or CURRENT/recent data
  you are not sure about → set is_confident = False, and leave answer_fa empty.
- Never guess specific numbers (pressure, temperature) for a named brand/model.
- Answer only in Persian.

## User Question:
{question}
"""

prompt_template = ChatPromptTemplate.from_template(LLM_KNOWLEDGE_PROMPT)


class LLMKnowledgeAnswer(BaseModel):
    is_confident: bool = Field(
        description="True only if you are sure this is general, stable knowledge."
    )
    answer_fa: str = Field(
        description="Persian answer. Empty string if is_confident is False."
    )


def get_llm_knowledge_answer(question: str) -> LLMKnowledgeAnswer:
    """Tries to answer directly from LLM knowledge. Used as fast-path before web search."""
    llm = ChatOpenAI(
        api_key=settings.OPENAI_API_KEY,
        model="gpt-4o-mini",
        temperature=0.0,
    )
    chain = prompt_template | llm.with_structured_output(LLMKnowledgeAnswer)
    result = chain.invoke({"question": question})
    logger.info(f"LLMKnowledge: is_confident=[{result.is_confident}]")
    return result