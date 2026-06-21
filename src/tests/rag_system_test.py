import chromadb
from chromadb.config import Settings
from src.config.setting import settings

client = chromadb.PersistentClient(
    path=settings.CHROMA_DB_DIR,
    settings=Settings(anonymized_telemetry=False),
)
collection = client.get_or_create_collection(name="technical_collection")

# Test 1 — no filter at all, just count + peek
print("Total count:", collection.count())
sample = collection.get(limit=3, include=["metadatas"])
print("Sample metadatas:", sample["metadatas"])

# Test 2 — apply the SAME filter technical_handler would use
result = collection.get(
    where={"brand": {"$eq": "CIM"}},
    limit=5,
    include=["metadatas"],
)
print("CIM filter count:", len(result["ids"]))

# Test 3 — no filter (matches your CLI search call with brand=None)
result_no_filter = collection.get(limit=5, include=["metadatas"])
print("No filter count:", len(result_no_filter["ids"]))