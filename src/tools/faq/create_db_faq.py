"""
create_db_faq.py
────────────────
یک‌بار اجرا میشه — هر وقت faq.json تغییر کرد.
هیچ وابستگی به retriever.py نداره.
"""

import json
import logging

import chromadb
from openai import OpenAI
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from src.config.setting import settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)


openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)

chroma_client = chromadb.PersistentClient(path="src/chroma_db/faq_collection")


EMBED_MODEL         = "text-embedding-3-large"
PASSAGE_INSTRUCTION = "متن پاسخ به سؤالات متداول:\n"

SYNTHETIC_VARIANTS = 4   


def _embed_passage(text: str) -> list[float]:
    response = openai_client.embeddings.create(
        model=EMBED_MODEL,
        input=PASSAGE_INSTRUCTION + text,
    )
    return response.data[0].embedding


_paraphrase_llm = ChatOpenAI(
    api_key=settings.OPENAI_API_KEY,
    model="gpt-4o-mini",
    temperature=0.7,
)

_paraphrase_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "شما یک دستیار هستید که جملات سؤالی فارسی می‌نویسید. "
     f"دقیقاً {SYNTHETIC_VARIANTS} نوع مختلف از همین سؤال بنویسید. "
     "سبک‌های مختلف را پوشش دهید: رسمی، غیررسمی، کوتاه، بلند. "
     "هر سؤال را در یک خط جداگانه بنویسید. "
     "هیچ شماره‌گذاری یا توضیح اضافی ندهید."),
    ("human",
     "سؤال اصلی: {question}\n"
     "پاسخ مرتبط: {answer}\n\n"
     f"{SYNTHETIC_VARIANTS} بازنویسی:")
])
_paraphrase_chain = _paraphrase_prompt | _paraphrase_llm | StrOutputParser()


def _generate_paraphrases(question: str, answer: str) -> list[str]:
    try:
        raw = _paraphrase_chain.invoke({"question": question, "answer": answer})
        variants = [line.strip() for line in raw.splitlines() if line.strip()]
        logger.info(f"  {len(variants)} synthetic variants generated.")
        return variants
    except Exception as e:
        logger.warning(f"  Paraphrase generation failed: {e}")
        return []



def build_faq_index(faq_path: str = "src/data/faq.json") -> None:
    with open(faq_path, "r", encoding="utf-8") as f:
        faq_data = json.load(f)

   
    try:
        chroma_client.delete_collection(name="faq")
        logger.info("Old collection deleted from disk.")
    except Exception:
        pass  # اگه collection وجود نداشت مشکلی نیست

    faq_collection = chroma_client.create_collection(
        name="faq",
        metadata={"hnsw:space": "cosine"}
    )
    logger.info("Fresh collection created.")

    ids        = []
    documents  = []
    embeddings = []
    metadatas  = []

    for intent_key, entry in faq_data.items():
        answer         = entry["answer"]
        human_variants = entry["variants"]

        logger.info(f"Processing: '{intent_key}'  ({len(human_variants)} human variants)")

        synthetic_variants = _generate_paraphrases(human_variants[0], answer)

        all_variants = (
            [(v, False) for v in human_variants] +
            [(v, True)  for v in synthetic_variants]
        )

        for i, (variant, is_synthetic) in enumerate(all_variants):
            label = "synth" if is_synthetic else "human"
            logger.info(f"  [{label}] {variant[:70]}")

            ids.append(f"{intent_key}_{i}")
            documents.append(variant)
            embeddings.append(_embed_passage(variant))
            metadatas.append({
                "intent":       intent_key,
                "answer":       answer,
                "source_text":  variant,
                "is_synthetic": str(is_synthetic),
            })

    if ids:
        faq_collection.upsert(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        logger.info(f"\nDone — {len(ids)} vectors for {len(faq_data)} intents.")


if __name__ == "__main__":
    build_faq_index()