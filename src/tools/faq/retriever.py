import logging
from functools import lru_cache

import chromadb
from openai import OpenAI
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from src.config.setting import settings

logger = logging.getLogger(__name__)


openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
llm           = ChatOpenAI(api_key=settings.OPENAI_API_KEY, model="gpt-4o", temperature=0.2)
fast_llm      = ChatOpenAI(api_key=settings.OPENAI_API_KEY, model="gpt-4o-mini", temperature=0)

chroma_client  = chromadb.PersistentClient(path="src/chroma_db/faq_collection")
faq_collection = chroma_client.get_or_create_collection(
    name="faq",
    metadata={"hnsw:space": "cosine"}
)


EMBED_MODEL       = "text-embedding-3-large"
QUERY_INSTRUCTION = "برای یافتن پاسخ سؤال زیر، متن مناسب را پیدا کن:\n"

HIGH_THRESHOLD = 0.78   
SOFT_THRESHOLD = 0.45   


def embed_query(text: str) -> list[float]:
    """Embed a user query with query-side instruction prefix."""
    return _embed(QUERY_INSTRUCTION + text)


def _embed(text: str) -> list[float]:
    response = openai_client.embeddings.create(
        model=EMBED_MODEL,
        input=text,
    )
    return response.data[0].embedding


@lru_cache(maxsize=512)
def _cached_embed_query(text: str) -> tuple[float, ...]:
    """Cached version of embed_query. Returns a tuple (hashable for lru_cache)."""
    return tuple(embed_query(text))



def _normalize_query(user_text: str) -> str:
    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "شما یک دستیار هوشمند هستید. "
         "وظیفه شما تبدیل جملات غیررسمی فارسی به یک سؤال رسمی و واضح است. "
         "فقط سؤال بازنویسی‌شده را برگردانید، هیچ توضیح اضافه‌ای ندهید."),
        ("human", "جمله ورودی: {query}\nسؤال رسمی:")
    ])
    chain = prompt | fast_llm | StrOutputParser()
    try:
        return chain.invoke({"query": user_text}).strip()
    except Exception as e:
        logger.warning(f"Query normalisation failed, using raw text: {e}")
        return user_text


def _query_chroma(embedding: list[float]) -> dict | None:
    """Run a single cosine query against ChromaDB. Returns raw result or None."""
    results = faq_collection.query(
        query_embeddings=[embedding],
        n_results=1,
        include=["metadatas", "distances"]
    )
    if not results["ids"][0]:
        return None
    distance   = results["distances"][0][0]
    similarity = 1 - distance
    return {
        "metadata":   results["metadatas"][0][0],
        "similarity": similarity,
    }


def _search_faq(user_text: str, trace=None) -> dict | None:
    """
    Two-stage search pipeline:

    Stage 1 — fast path (raw embed, cached):
        Embed user_text as-is. If similarity >= HIGH_THRESHOLD → return immediately.
        No LLM call, no extra latency, result is cached for repeats.

    Stage 2 — slow path (normalise → embed):
        Only reached when raw similarity < HIGH_THRESHOLD.
        gpt-4o-mini rewrites the colloquial query to formal Persian,
        then we embed the cleaned version and search again.
        The normalised text is also cached so identical colloquial
        phrasings only pay the normalisation cost once.
    """
    # ── Stage 1: fast path ───────────────────────────────────────────────
    raw_vec    = list(_cached_embed_query(user_text))
    raw_result = _query_chroma(raw_vec)

    if trace and raw_result:
        trace.raw_similarity = raw_result["similarity"]

    if raw_result and raw_result["similarity"] >= HIGH_THRESHOLD:
        logger.debug(f"Fast-path hit  sim={raw_result['similarity']:.4f}  '{user_text}'")
        return raw_result

    # ── Stage 2: slow path — normalise then re-embed ─────────────────────
    normalised = _normalize_query(user_text)
    logger.debug(f"Normalised: '{user_text}' → '{normalised}'")

    if trace:
        trace.normalized_query = normalised

    if normalised == user_text:
        # Normalisation returned identical text → reuse raw result, skip re-embed
        return raw_result

    norm_vec    = list(_cached_embed_query(normalised))
    norm_result = _query_chroma(norm_vec)

    # Return whichever search gave the higher similarity score
    if norm_result and (
        raw_result is None or norm_result["similarity"] >= raw_result["similarity"]
    ):
        logger.debug(f"Slow-path winner  sim={norm_result['similarity']:.4f}")
        return norm_result

    return raw_result

def _handle_soft_match(user_text: str, hint_answer: str) -> str:
    """similarity between SOFT and HIGH — use the FAQ answer as an LLM hint."""
    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "شما یک دستیار مفید برای شرکت CEC (تولیدکننده شیرآلات صنعتی) هستید. "
         "سیستم یک پاسخ احتمالاً مرتبط از پایگاه داده پیدا کرده است. "
         "اگر پاسخ مرتبط است، آن را به طور طبیعی و مودبانه ادغام کنید. "
         "اگر مطمئن نیستید، عدم اطمینان را ذکر کرده و برای توضیح بیشتر بخواهید."),
        ("human",
         "سؤال کاربر: {query}\n\n"
         "پاسخ احتمالی از پایگاه داده: {hint}\n\n"
         "لطفاً به فارسی پاسخ دهید.")
    ])
    chain = prompt | llm | StrOutputParser()
    return chain.invoke({"query": user_text, "hint": hint_answer})


def _handle_llm_fallback(user_text: str, history: list = None) -> str:
    """No FAQ match — answer from LLM knowledge with optional conversation history."""
    messages = [
        ("system",
         "شما یک مهندس پشتیبانی فنی ارشد در شرکت CEC هستید، "
         "شرکتی که شیرآلات صنعتی تولید می‌کند. "
         "سؤال را بر اساس دانش خود پاسخ دهید. به فارسی پاسخ دهید.")
    ]
    if history:
        for msg in history[:-1]:
            messages.append((msg["role"], msg["content"]))
    messages.append(("human", "{query}"))

    prompt = ChatPromptTemplate.from_messages(messages)
    chain  = prompt | llm | StrOutputParser()
    return chain.invoke({"query": user_text})


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def get_chat_response(user_text: str, history: list = None, trace=None) -> str:
    """
    Runtime FAQ response pipeline:

    ┌─────────────────────────────────────────────────────────────────┐
    │  embed raw query (cached)                                       │
    │       │                                                         │
    │       ├── sim >= 0.78 ──────────────────► return FAQ answer     │  ~200ms
    │       │                                   (fast path, no LLM)   │
    │       │                                                         │
    │       └── sim < 0.78 → gpt-4o-mini normalize → re-embed         │
    │                              │                                  │
    │                              ├── sim >= 0.78 ──► return answer  │  ~500ms
    │                              │                                  │
    │                              ├── sim >= 0.45 ──► gpt-4o hint    │  ~2.0s
    │                              │                                  │
    │                              └── sim < 0.45  ──► gpt-4o free    │  ~2.0s
    └─────────────────────────────────────────────────────────────────┘
    """
    try:
        result = _search_faq(user_text, trace=trace)

        if result:
            similarity = result["similarity"]
            answer     = result["metadata"]["answer"]

            if similarity >= HIGH_THRESHOLD:
                if trace:
                    trace.path = "fast_path"
                    trace.matched_answer_preview = answer[:200]
                return answer

            if similarity >= SOFT_THRESHOLD:
                if trace:
                    trace.path = "soft_match"
                    trace.matched_answer_preview = answer[:200]
                return _handle_soft_match(user_text, answer)

    except Exception as e:
        logger.error(f"FAQ search failed: {e}")

    if trace:
        trace.path = "llm_fallback"
    return _handle_llm_fallback(user_text, history=history)