import json
import logging
import argparse
from pathlib import Path
from typing import Optional
import chromadb
from chromadb.config import Settings
from openai import OpenAI
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from src.config.setting import settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────

EXTRACTED_DIR = Path("src/data/catalog/extracted")
COLLECTION_NAME = "technical_collection"
CONFIDENCE_THRESHOLD = 0.60


# ─────────────────────────────────────────────
# ChromaDB Client
# ─────────────────────────────────────────────

def get_chroma_client() -> chromadb.ClientAPI:
    """Returns persistent ChromaDB client."""
    return chromadb.PersistentClient(
        path=settings.CHROMA_DB_DIR,
        settings=Settings(anonymized_telemetry=False),
    )


def get_collection(client: chromadb.ClientAPI):
    """Returns or creates technical_collection."""
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


# ─────────────────────────────────────────────
# Embedding
# ─────────────────────────────────────────────

def embed_texts(texts: list[str], openai_client: OpenAI) -> list[list[float]]:
    """Embeds texts using text-embedding-3-large with batching."""
    BATCH_SIZE = 100
    all_embeddings = []

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i:i + BATCH_SIZE]
        response = openai_client.embeddings.create(
            model=settings.EMBEDDING_MODEL,
            input=batch,
        )
        batch_embeddings = [item.embedding for item in response.data]
        all_embeddings.extend(batch_embeddings)
        logger.info(f"Embedded batch {i // BATCH_SIZE + 1} ({len(batch)} texts)")

    return all_embeddings


def build_enriched_content(chunk: dict, chunk_type: str) -> str:
    """
    Adds product info at the top of content before embedding.
    This makes search much more accurate!

    Example output:
        نام محصول: Cim 30-30A
        نوع محصول: شیر یکطرفه
        برند: CIM
        کاربرد: سیستم های آب آشامیدنی

        [actual content here]
    """
    meta = chunk.get("metadata", {})
    product_name = chunk.get("product_name") or ""
    product_type = meta.get("product_type") or ""
    brand = chunk.get("brand") or ""
    applications = meta.get("applications") or ""
    material = meta.get("material") or ""
    pressure = meta.get("pressure") or ""
    max_temp = meta.get("max_temp") or ""

    header = f"""نام محصول: {product_name}
نوع محصول: {product_type}
برند: {brand}
فشار کاری: {pressure}
حداکثر دما: {max_temp}
جنس: {material}
کاربرد: {applications}
"""

    if chunk_type == "general":
        raw_content = (chunk.get("general_content") or "").strip()
    else:
        raw_content = (chunk.get("table_content") or "").strip()

    return f"{header}\n{raw_content}"


# ─────────────────────────────────────────────
# Initialization — Load JSON → ChromaDB
# ─────────────────────────────────────────────

def load_json_files() -> list[dict]:
    """Loads all extracted JSON catalog files."""
    all_chunks = []
    json_files = list(EXTRACTED_DIR.glob("*_extracted.json"))

    if not json_files:
        logger.warning(f"No extracted JSON files found in {EXTRACTED_DIR}")
        return []

    for json_file in json_files:
        logger.info(f"Loading: {json_file.name}")
        with open(json_file, "r", encoding="utf-8") as f:
            chunks = json.load(f)
        all_chunks.extend(chunks)
        logger.info(f"Loaded {len(chunks)} chunks from {json_file.name}")

    logger.info(f"Total chunks loaded: {len(all_chunks)}")
    return all_chunks


def initialize_chromadb():
    """
    One-time initialization:
    Loads JSON → enriches content → embeds → saves to ChromaDB.
    Safe to run multiple times — skips already embedded chunks.
    """
    openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
    chroma_client = get_chroma_client()
    collection = get_collection(chroma_client)

    all_chunks = load_json_files()
    if not all_chunks:
        logger.error("No chunks to embed!")
        return

    existing = collection.get(include=[])
    existing_ids = set(existing["ids"])
    logger.info(f"Already embedded chunks: {len(existing_ids)}")

    to_embed = []

    for chunk in all_chunks:
        if not chunk.get("product_name"):
            continue

        base_metadata = {
            "product_name": chunk["metadata"].get("product_name", ""),
            "product_type": chunk["metadata"].get("product_type", ""),
            "brand": chunk["metadata"].get("brand", ""),
            "max_temp": chunk["metadata"].get("max_temp") or "",
            "pressure": chunk["metadata"].get("pressure") or "",
            "sizes": json.dumps(chunk["metadata"].get("sizes", []), ensure_ascii=False),
            "standards": json.dumps(chunk["metadata"].get("standards", []), ensure_ascii=False),
            "applications": chunk["metadata"].get("applications") or "",
            "material": chunk["metadata"].get("material") or "",
            "connection_type": chunk["metadata"].get("connection_type") or "",
            "page_num": chunk["metadata"].get("page_num", 0),
            "source": chunk["metadata"].get("source", ""),
        }

        # General content chunk — enriched
        general_id = f"{chunk['chunk_id']}_general"
        general_content = (chunk.get("general_content") or "").strip()
        if general_id not in existing_ids and general_content:
            enriched = build_enriched_content(chunk, "general")
            to_embed.append({
                "id": general_id,
                "content": enriched,
                "metadata": {**base_metadata, "chunk_type": "general"},
            })

        # Table content chunk — enriched
        table_id = f"{chunk['chunk_id']}_table"
        table_content = (chunk.get("table_content") or "").strip()
        if table_id not in existing_ids and table_content:
            enriched = build_enriched_content(chunk, "table")
            to_embed.append({
                "id": table_id,
                "content": enriched,
                "metadata": {**base_metadata, "chunk_type": "table"},
            })

    if not to_embed:
        logger.info("All chunks already embedded! Nothing to do.")
        return

    logger.info(f"Chunks to embed: {len(to_embed)}")

    texts = [item["content"] for item in to_embed]
    embeddings = embed_texts(texts, openai_client)

    collection.add(
        ids=[item["id"] for item in to_embed],
        embeddings=embeddings,
        documents=[item["content"] for item in to_embed],
        metadatas=[item["metadata"] for item in to_embed],
    )

    logger.info(f"✅ Successfully embedded {len(to_embed)} chunks!")
    print(f"\n✅ Done! {len(to_embed)} chunks saved to [{COLLECTION_NAME}]")


def reset_collection():
    """Deletes and recreates technical_collection for re-embedding."""
    chroma_client = get_chroma_client()
    try:
        chroma_client.delete_collection(COLLECTION_NAME)
        logger.info(f"Deleted collection: {COLLECTION_NAME}")
    except Exception:
        pass
    initialize_chromadb()


# ─────────────────────────────────────────────
# Search
# ─────────────────────────────────────────────

class RAGSearchResult:
    """Result from RAG search."""
    def __init__(self, content: str, metadata: dict, score: float):
        self.content = content
        self.metadata = metadata
        self.score = score
        self.passed_threshold = score >= CONFIDENCE_THRESHOLD

    def __repr__(self):
        return (
            f"RAGSearchResult("
            f"product={self.metadata.get('product_name')}, "
            f"type={self.metadata.get('chunk_type')}, "
            f"score={self.score:.3f})"
        )


def search_catalog(
    query: str,
    brand: Optional[str] = None,
    product_name: Optional[str] = None,
    chunk_type: Optional[str] = None,
    top_k: int = 3,
) -> list[RAGSearchResult]:
    """Searches ChromaDB technical_collection for relevant chunks."""
    openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
    chroma_client = get_chroma_client()
    collection = get_collection(chroma_client)

    query_embedding = openai_client.embeddings.create(
        model=settings.EMBEDDING_MODEL,
        input=[query],
    ).data[0].embedding

    where_filter = {}
    conditions = []

    if brand:
        conditions.append({"brand": {"$eq": brand.upper()}})
    if product_name:
        conditions.append({"product_name": {"$eq": product_name}})
    if chunk_type:
        conditions.append({"chunk_type": {"$eq": chunk_type}})

    if len(conditions) == 1:
        where_filter = conditions[0]
    elif len(conditions) > 1:
        where_filter = {"$and": conditions}

    search_kwargs = {
        "query_embeddings": [query_embedding],
        "n_results": top_k,
        "include": ["documents", "metadatas", "distances"],
    }
    if where_filter:
        search_kwargs["where"] = where_filter

    results = collection.query(**search_kwargs)

    search_results = []
    if results and results["ids"] and results["ids"][0]:
        for doc, meta, distance in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            score = 1 - distance
            search_results.append(RAGSearchResult(
                content=doc,
                metadata=meta,
                score=score,
            ))

    logger.info(f"RAG search found {len(search_results)} results for: [{query[:50]}]")
    for r in search_results:
        logger.info(f"  → {r}")

    return search_results


# ─────────────────────────────────────────────
# CRAG — Verification with GPT-4o mini
# ─────────────────────────────────────────────

class CRAGDecision(BaseModel):
    is_relevant: bool = Field(
        description="True if any result answers the user question. False if none are relevant."
    )
    best_result_index: Optional[int] = Field(
        None,
        description="Index of the best result (0, 1, or 2). None if is_relevant is False."
    )

CRAG_PROMPT = """
You are a technical assistant for industrial valves.
A user asked a question and we found some results from our catalog.
Decide if any result is relevant to the user question.

## User Question:
{question}

## Catalog Results:
{results}

## Your Job:
- Check if any result actually answers the user question
- If yes → set is_relevant=True and pick the best result index (0, 1, or 2)
- If no result is relevant → set is_relevant=False
- Be strict — only mark relevant if the result clearly relates to the question
"""

crag_prompt_template = ChatPromptTemplate.from_template(CRAG_PROMPT)


def verify_with_crag(
    question: str,
    results: list[RAGSearchResult],
) -> CRAGDecision:
    """
    Uses GPT-4o mini to verify if RAG results are relevant.
    Called by technical_handler.py after search_catalog().
    """
    llm = ChatOpenAI(
        api_key=settings.OPENAI_API_KEY,
        model="gpt-4o-mini",
        temperature=0.0,
    )
    structured_llm = llm.with_structured_output(CRAGDecision)
    chain = crag_prompt_template | structured_llm

    # Format results for LLM — NO scores shown!
    formatted_results = ""
    for i, result in enumerate(results):
        formatted_results += f"""
Result {i}:
Product: {result.metadata.get('product_name')}
Type: {result.metadata.get('product_type')}
Brand: {result.metadata.get('brand')}
Content: {result.content[:500]}
---"""

    decision = chain.invoke({
        "question": question,
        "results": formatted_results,
    })

    logger.info(
        f"CRAG decision: relevant={decision.is_relevant} "
        f"best_index={decision.best_result_index} "
    )

    return decision


# ─────────────────────────────────────────────
# Stats
# ─────────────────────────────────────────────

def get_collection_stats() -> dict:
    """Returns stats about the technical collection."""
    chroma_client = get_chroma_client()
    collection = get_collection(chroma_client)
    count = collection.count()
    return {
        "collection_name": COLLECTION_NAME,
        "total_chunks": count,
    }


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RAG System — Technical Collection")
    parser.add_argument("--init", action="store_true", help="Initialize ChromaDB from JSON files")
    parser.add_argument("--reset", action="store_true", help="Delete and re-embed everything")
    parser.add_argument("--stats", action="store_true", help="Show collection stats")
    parser.add_argument("--search", type=str, help="Test search query")
    args = parser.parse_args()

    if args.init:
        print("Initializing ChromaDB technical collection...")
        initialize_chromadb()

    elif args.reset:
        print("Resetting ChromaDB technical collection...")
        reset_collection()

    elif args.stats:
        stats = get_collection_stats()
        print(f"\nCollection: {stats['collection_name']}")
        print(f"Total chunks: {stats['total_chunks']}")

    elif args.search:
        print(f"\nSearching for: {args.search}")
        results = search_catalog(args.search, top_k=3)
        print(f"\nFound {len(results)} results — running CRAG verification...")
        decision = verify_with_crag(args.search, results)
        print(f"\nCRAG Decision:")
        print(f"  Relevant: {decision.is_relevant}")
        print(f"  Best result: {decision.best_result_index}")
        if decision.is_relevant and decision.best_result_index is not None:
            best = results[decision.best_result_index]
            print(f"\nBest Result:")
            print(f"  Product: {best.metadata.get('product_name')}")
            print(f"  Content: {best.content[:300]}")

    else:
        print("Usage:")
        print("  Initialize:  python3 -m src.tools.technical.rag_system --init")
        print("  Reset:       python3 -m src.tools.technical.rag_system --reset")
        print("  Stats:       python3 -m src.tools.technical.rag_system --stats")
        print("  Test search: python3 -m src.tools.technical.rag_system --search 'شیر یکطرفه'")