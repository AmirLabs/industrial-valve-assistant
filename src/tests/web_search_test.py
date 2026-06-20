"""
Web Searcher Test — WITH LATENCY BREAKDOWN
============================================
Run with:
    python -m src.tests.test_web_searcher
"""

import time
from src.tools.technical.web_searcher import WebSearcher

TEST_QUESTIONS = [
    "استاندارد PN16 یعنی چی؟",
]


def test_web_search_timed():
    searcher = WebSearcher()

    for question in TEST_QUESTIONS:
        print("\n" + "=" * 60)
        print(f"❓ Question: {question}")
        print("=" * 60)

        total_start = time.time()

        # Step 1: Query transform
        t1 = time.time()
        transformed = searcher.transform_query(question)
        t1_duration = time.time() - t1
        print(f"\n⏱️  Step 1 — Query Transform: {t1_duration:.2f}s")
        print(f"   English query: {transformed.english_query}")

        # Step 2: Tavily search
        t2 = time.time()
        results = searcher.search(transformed.english_query)
        t2_duration = time.time() - t2
        print(f"\n⏱️  Step 2 — Tavily Search: {t2_duration:.2f}s")
        print(f"   Results found: {len(results)}")

        # Step 3: Generate answer
        t3 = time.time()
        answer = searcher.generate_answer(question, results)
        t3_duration = time.time() - t3
        print(f"\n⏱️  Step 3 — Generate Answer: {t3_duration:.2f}s")

        total_duration = time.time() - total_start

        print(f"\n{'='*60}")
        print(f"📊 LATENCY BREAKDOWN:")
        print(f"{'='*60}")
        print(f"  Query Transform:  {t1_duration:.2f}s  ({t1_duration/total_duration*100:.0f}%)")
        print(f"  Tavily Search:    {t2_duration:.2f}s  ({t2_duration/total_duration*100:.0f}%)")
        print(f"  Generate Answer:  {t3_duration:.2f}s  ({t3_duration/total_duration*100:.0f}%)")
        print(f"  {'─'*40}")
        print(f"  TOTAL:            {total_duration:.2f}s")
        print(f"\n📝 Answer:\n{answer.answer_fa}")


if __name__ == "__main__":
    test_web_search_timed()