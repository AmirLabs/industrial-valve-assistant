"""
GPT-4o vs GPT-4o Mini Vision Comparison Test
=============================================
Compares text/table extraction quality and cost on one catalog page.
Run with:
    python src/tests/test_vision_compare.py
"""

import os
import base64
import time
from pathlib import Path
from pdf2image import convert_from_path
from openai import OpenAI
from src.config.setting import settings

CATALOG_PATH = "src/data/catalog/cim-catalog.pdf"
TEST_PAGE = 10

# ─────────────────────────────────────────────
# Prompt
# ─────────────────────────────────────────────

EXTRACTION_PROMPT = """
You are an expert assistant for industrial valve catalogs.
Analyze this catalog page and extract the following:

1. All TEXT content (Persian and English)
2. All TABLES — convert every table to clean markdown format

## IMPORTANT RULES:
- IGNORE all diagrams, drawings, and engineering illustrations
- IGNORE page numbers and decorative elements
- EXTRACT all product names exactly as written
- EXTRACT all specifications (pressure, temperature, standards, applications)
- CONVERT every table to markdown format like this:
  | Column1 | Column2 |
  |---------|---------|
  | value1  | value2  |

## OUTPUT FORMAT:
Return your response in this exact structure:

### PRODUCT NAME:
(product name here)

### TEXT CONTENT:
(all extracted text here)

### TABLES:
(all tables in markdown format here)

### METADATA:
- Brand: 
- Product Type (in Persian):
- Max Temperature:
- Working Pressure:
- Standards:
- Applications:
"""

# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def pdf_page_to_base64(pdf_path: str, page_num: int) -> str:
    """Converts a PDF page to base64 encoded image."""
    images = convert_from_path(
        pdf_path,
        first_page=page_num,
        last_page=page_num,
        dpi=150,
    )
    if not images:
        raise ValueError(f"Could not convert page {page_num} to image!")

    temp_path = "src/tests/temp_vision_page.jpg"
    images[0].save(temp_path, "JPEG")

    with open(temp_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")

    os.remove(temp_path)
    return encoded


def call_vision_model(client: OpenAI, model: str, image_base64: str) -> tuple[str, float]:
    """
    Calls OpenAI vision model with the catalog page image.
    Returns (response_text, duration_seconds)
    """
    start_time = time.time()

    response = client.chat.completions.create(
        model=model,
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

    duration = time.time() - start_time
    result_text = response.choices[0].message.content

    # Token usage
    input_tokens = response.usage.prompt_tokens
    output_tokens = response.usage.completion_tokens

    return result_text, duration, input_tokens, output_tokens


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculates approximate API cost in USD."""
    costs = {
        "gpt-4o": {"input": 2.50, "output": 10.00},
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    }
    if model not in costs:
        return 0.0
    input_cost = (input_tokens / 1_000_000) * costs[model]["input"]
    output_cost = (output_tokens / 1_000_000) * costs[model]["output"]
    return input_cost + output_cost


# ─────────────────────────────────────────────
# Main Test
# ─────────────────────────────────────────────

def test_vision_comparison():
    print("\n🚀 GPT-4o vs GPT-4o Mini — Vision Comparison Test")
    print(f"📄 Catalog: {CATALOG_PATH}")
    print(f"📑 Testing page: {TEST_PAGE}\n")

    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    # Convert page to base64 once — use for both models
    print("⏳ Converting PDF page to image...")
    image_base64 = pdf_page_to_base64(CATALOG_PATH, TEST_PAGE)
    print("✅ Page converted successfully!\n")

    models = ["gpt-4o-mini", "gpt-4o"]
    results = {}

    for model in models:
        print(f"{'='*60}")
        print(f"⏳ Testing model: {model}")
        print(f"{'='*60}")

        text, duration, input_tokens, output_tokens = call_vision_model(
            client, model, image_base64
        )
        cost = calculate_cost(model, input_tokens, output_tokens)
        results[model] = {
            "text": text,
            "duration": duration,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": cost,
        }

        print(f"✅ Done in {duration:.1f}s")
        print(f"📊 Tokens: input={input_tokens} output={output_tokens}")
        print(f"💰 Cost: ${cost:.6f}")
        print(f"\n📝 Output:\n")
        print(text)
        print()

    # Final comparison summary
    print("\n" + "="*60)
    print("📊 COMPARISON SUMMARY")
    print("="*60)
    print(f"{'Model':<20} {'Time':<12} {'Cost':<15} {'Output Tokens'}")
    print("-"*60)
    for model, data in results.items():
        print(
            f"{model:<20} "
            f"{data['duration']:.1f}s{'':<7} "
            f"${data['cost']:.6f}{'':<5} "
            f"{data['output_tokens']}"
        )

    print("\n🎯 Test Complete!")
    print("Check outputs above and decide which model fits your needs!")


if __name__ == "__main__":
    test_vision_comparison()