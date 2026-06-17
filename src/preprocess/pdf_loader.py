import os
import json
import base64
import argparse
import logging
import time
from pathlib import Path
from pdf2image import convert_from_path
from openai import OpenAI
from src.config.setting import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────

CATALOG_DIR = Path("src/data/catalog")
OUTPUT_DIR = Path("src/data/catalog/extracted")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BRAND_MAP = {
    "cim": "CIM",
    "farab": "FARAB",
    "mirab": "MIRAB",
    "kiz": "KIZIRAN",
}

# Cost tracking (GPT-4o pricing)
COST_PER_1M_INPUT = 2.50
COST_PER_1M_OUTPUT = 10.00

# ─────────────────────────────────────────────
# Prompt
# ─────────────────────────────────────────────

EXTRACTION_PROMPT = """
You are an expert assistant for industrial valve catalogs.
Analyze this catalog page and extract structured information.

## STRICT RULES:
- STRICTLY IGNORE all engineering drawings, dimension diagrams, pressure/flow charts, and any visual illustrations
- STRICTLY IGNORE page numbers, headers, footers, and decorative elements
- NEVER guess or fabricate information — if something is not clearly written on the page, return null
- Extract BOTH Persian and English text exactly as written
- Convert ALL tables to clean markdown format

## EXTRACT THE FOLLOWING:

### 1. PRODUCT NAME
Exact product name/code as written (e.g. "Cim 80", "BVW#150")

### 2. GENERAL CONTENT
All descriptive text about the product:
- Product description
- Material/parts list
- Technical specifications
- Standards
- Applications
- Any other text (Persian and English)

### 3. TABLE CONTENT
Convert every table to markdown format:
| Column1 | Column2 | Column3 |
|---------|---------|---------|
| value1  | value2  | value3  |

### 4. METADATA
Extract these specific fields:
- product_type: valve type in Persian (e.g. شیر یکطرفه، شیر فلکه کشویی)
- max_temp: maximum working temperature (e.g. "180°C")
- pressure: working pressure (e.g. "PN16", "16 bar")
- sizes: list of available sizes exactly as written (e.g. ["1/2\"", "3/4\"", "1\"", "2\""] or ["DN50", "DN100"])
- standards: list of standards (e.g. ["BS 5154", "ISO 9001", "EN 12266-1"])
- applications: what this valve is used for (Persian preferred)
- material: main body material (e.g. "برنج", "چدن", "فولاد")
- connection_type: how valve connects to pipe — choose from: رزوه، فلنج، ویفری، جوشی (or null if not clear)

## RESPONSE FORMAT:
Return ONLY a valid JSON object with NO extra text, NO markdown backticks:

{
  "product_name": "...",
  "general_content": "...",
  "table_content": "...",
  "metadata": {
    "product_type": "...",
    "max_temp": "...",
    "pressure": "...",
    "sizes": [],
    "standards": [],
    "applications": "...",
    "material": "...",
    "connection_type": "..."
  }
}

If this page has NO useful product information (cover page, table of contents, blank page) return:
{"skip": true, "reason": "..."}
"""

# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def find_catalog_file(catalog_key: str) -> Path:
    """Finds catalog PDF file by brand key."""
    for pdf_file in CATALOG_DIR.glob("*.pdf"):
        if catalog_key.lower() in pdf_file.name.lower():
            return pdf_file
    raise FileNotFoundError(f"No catalog found for: {catalog_key}")


def get_output_path(catalog_key: str) -> Path:
    """Returns output JSON path for a catalog."""
    brand = BRAND_MAP.get(catalog_key.lower(), catalog_key.upper())
    return OUTPUT_DIR / f"{brand.lower()}_extracted.json"


def load_existing_results(output_path: Path) -> list:
    """Loads existing results from JSON to avoid reprocessing."""
    if output_path.exists():
        with open(output_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_results(results: list, output_path: Path) -> None:
    """Saves results to JSON file."""
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


def get_processed_pages(results: list) -> set:
    """Returns set of already processed page numbers."""
    return {r["metadata"]["page_num"] for r in results if "metadata" in r}


def page_to_base64(pdf_path: Path, page_num: int) -> str:
    """Converts PDF page to base64 image."""
    images = convert_from_path(
        str(pdf_path),
        first_page=page_num,
        last_page=page_num,
        dpi=200,
    )
    if not images:
        raise ValueError(f"Could not convert page {page_num}")

    temp_path = OUTPUT_DIR / "temp_page.jpg"
    images[0].save(str(temp_path), "JPEG")

    with open(temp_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")

    temp_path.unlink()
    return encoded


def calculate_cost(input_tokens: int, output_tokens: int) -> float:
    """Calculates GPT-4o API cost in USD."""
    input_cost = (input_tokens / 1_000_000) * COST_PER_1M_INPUT
    output_cost = (output_tokens / 1_000_000) * COST_PER_1M_OUTPUT
    return input_cost + output_cost


# ─────────────────────────────────────────────
# Core Processing
# ─────────────────────────────────────────────

def process_page(
    client: OpenAI,
    pdf_path: Path,
    page_num: int,
    brand: str,
    source: str,
) -> dict | None:
    """
    Processes a single PDF page with GPT-4o Vision.
    Returns a chunk dict or None if page should be skipped.
    """
    logger.info(f"Processing page {page_num}...")

    # Convert page to image
    image_base64 = page_to_base64(pdf_path, page_num)

    # Call GPT-4o Vision
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}",
                            "detail": "high",
                        },
                    },
                    {
                        "type": "text",
                        "text": EXTRACTION_PROMPT,
                    },
                ],
            }
        ],
        max_tokens=2000,
    )

    # Track cost
    input_tokens = response.usage.prompt_tokens
    output_tokens = response.usage.completion_tokens
    cost = calculate_cost(input_tokens, output_tokens)

    raw_text = response.choices[0].message.content.strip()

    # Parse JSON response
    try:
        # Remove markdown backticks if LLM added them
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]

        data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        logger.error(f"Page {page_num}: JSON parse error: {e}")
        logger.error(f"Raw response: {raw_text[:500]}")
        return None, cost

    # Skip useless pages
    if data.get("skip"):
        logger.info(f"Page {page_num}: Skipped — {data.get('reason', 'no reason given')}")
        return None, cost

    # Build chunk
    chunk = {
        "chunk_id": f"{source}_page{page_num}",
        "product_name": data.get("product_name", ""),
        "brand": brand,
        "general_content": data.get("general_content", ""),
        "table_content": data.get("table_content", ""),
        "metadata": {
            "product_name": data.get("product_name", ""),
            "product_type": data.get("metadata", {}).get("product_type", ""),
            "brand": brand,
            "max_temp": data.get("metadata", {}).get("max_temp"),
            "pressure": data.get("metadata", {}).get("pressure"),
            "sizes": data.get("metadata", {}).get("sizes", []),
            "standards": data.get("metadata", {}).get("standards", []),
            "applications": data.get("metadata", {}).get("applications"),
            "material": data.get("metadata", {}).get("material"),
            "connection_type": data.get("metadata", {}).get("connection_type"),
            "page_num": page_num,
            "source": source,
        },
    }

    return chunk, cost


# ─────────────────────────────────────────────
# Main Runner
# ─────────────────────────────────────────────

def run_catalog(catalog_key: str, test_page: int = None):
    """
    Processes one catalog.
    If test_page is given → only process that page.
    """
    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    pdf_path = find_catalog_file(catalog_key)
    brand = BRAND_MAP.get(catalog_key.lower(), catalog_key.upper())
    source = pdf_path.stem.lower().replace(" ", "-")
    output_path = get_output_path(catalog_key)

    # Load existing results to avoid reprocessing
    results = load_existing_results(output_path)
    processed_pages = get_processed_pages(results)

    logger.info(f"Catalog: {pdf_path.name}")
    logger.info(f"Brand: {brand}")
    logger.info(f"Output: {output_path}")
    logger.info(f"Already processed pages: {len(processed_pages)}")

    # Get total pages
    from pdf2image import pdfinfo_from_path
    info = pdfinfo_from_path(str(pdf_path))
    total_pages = info["Pages"]
    logger.info(f"Total pages: {total_pages}")

    # Decide which pages to process
    if test_page:
        pages_to_process = [test_page]
        logger.info(f"TEST MODE — processing only page {test_page}")
    else:
        pages_to_process = [
            p for p in range(1, total_pages + 1)
            if p not in processed_pages
        ]
        logger.info(f"Pages to process: {len(pages_to_process)}")

    # Process pages
    total_cost = 0.0
    success_count = 0

    for page_num in pages_to_process:
        try:
            chunk, cost = process_page(client, pdf_path, page_num, brand, source)
            total_cost += cost

            if chunk:
                results.append(chunk)
                success_count += 1
                logger.info(
                    f"✅ Page {page_num}: [{chunk['product_name']}] "
                    f"cost=${cost:.5f} total=${total_cost:.5f}"
                )
            else:
                logger.info(f"⏭️  Page {page_num}: Skipped — cost=${cost:.5f}")

            # Save after every page — protect against failures!
            save_results(results, output_path)

            # Small delay to avoid rate limits
            time.sleep(0.5)

        except Exception as e:
            logger.error(f"❌ Page {page_num}: Error — {e}", exc_info=True)
            # Save what we have so far
            save_results(results, output_path)

    # Final summary
    print("\n" + "=" * 60)
    print(f"✅ Done! Processed {success_count} pages")
    print(f"💰 Total cost: ${total_cost:.5f}")
    print(f"📁 Saved to: {output_path}")
    print("=" * 60)


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PDF Catalog Loader")
    parser.add_argument("--catalog", type=str, help="Catalog key: cim, farab, mirab, kiz")
    parser.add_argument("--test", action="store_true", help="Test mode — one page only")
    parser.add_argument("--page", type=int, default=10, help="Page to test (default: 10)")
    parser.add_argument("--all", action="store_true", help="Process all catalogs")
    args = parser.parse_args()

    if args.all:
        for key in BRAND_MAP.keys():
            print(f"\n{'='*60}")
            print(f"Processing catalog: {key}")
            print(f"{'='*60}")
            run_catalog(key)
    elif args.catalog:
        test_page = args.page if args.test else None
        run_catalog(args.catalog, test_page=test_page)
    else:
        print("Usage:")
        print("  Test one page:    python3 -m src.preprocess.pdf_loader --catalog cim --test --page 10")
        print("  Full catalog:     python3 -m src.preprocess.pdf_loader --catalog cim")
        print("  All catalogs:     python3 -m src.preprocess.pdf_loader --all")