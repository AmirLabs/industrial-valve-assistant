import json
from pathlib import Path

from rapidfuzz import fuzz, process

from src.preprocess.text_cleaning import (
    SYNONYMS_JSON_PATH,
    clean_text
)

# --------------------------------------------------
# Paths
# --------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parents[2]

LOG_DIR = ROOT_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

LOG_FILE = LOG_DIR / "alias_threshold.log"

# --------------------------------------------------
# Test Inputs
# --------------------------------------------------

TEST_INPUTS = [

    # شیرصافی
    "صافی",
    "شیر صافی",
    "شیرصافیی",
    "شیرسافی",
    "سیرصافی",

    # شیرفلکه کشویی
    "کشویی",
    "گشویی",
    "شیرفلکه کشوی",
    "شیر فلکه کشویی",

    # شیرویفری اهرمی
    "ویفری اهرمی",
    "ویفری ارمی",
    "ویفری احرمی",
    "شیر ویفری اهرمی",

    # شیرویفری گیربگسدار
    "ویفری گیربگسدار",
    "ویفری گیربکسدار",
    "ویفری گیربکس دار",
    "ویفری گیربکس",

    # شیریکطرفه زبانه لاستیکی
    "یکطرفه زبانه لاستیکی",
    "یک طرفه زبانه لاستیکی",
    "یکطرفه لاستیکی",
    "یکطرفه زبانه لاسیتکی",

    # شیر فشارشکن
    "فشارشکن",
    "فشار شکن",
    "فشارشگن",
    "فشارشکنن",

    # شیرفلکه سوزنی
    "سوزنی",
    "فلکه سوزنی",
    "فلکه سزنی",
    "سوزنیی",

    # شیرکشویی رینگ برنزی
    "کشویی رینگ برنزی",
    "شیر کشویی رینگ برنزی",
    "کشویی رینگ برنزیی",
    "کشویی رینگ برنزیه",
]


def test_alias_scores():

    with open(SYNONYMS_JSON_PATH, "r", encoding="utf-8") as f:
        alias_map = json.load(f)

    alias_keys = list(alias_map.keys())

    scores = []

    with open(LOG_FILE, "w", encoding="utf-8") as log:

        log.write("=" * 100 + "\n")
        log.write("ALIAS SCORE ANALYSIS\n")
        log.write("=" * 100 + "\n\n")

        for user_input in TEST_INPUTS:

            cleaned = clean_text(user_input)

            best_match = process.extractOne(
                cleaned,
                alias_keys,
                scorer=fuzz.QRatio
            )

            if not best_match:
                continue

            matched_alias = best_match[0]
            score = round(best_match[1], 2)

            scores.append(score)

            log.write(f"INPUT : {user_input}\n")
            log.write(f"MATCH : {matched_alias}\n")
            log.write(f"SCORE : {score}\n")
            log.write("-" * 60 + "\n")

        log.write("\n")
        log.write("=" * 100 + "\n")
        log.write("STATISTICS\n")
        log.write("=" * 100 + "\n")

        log.write(f"MIN SCORE : {min(scores):.2f}\n")
        log.write(f"MAX SCORE : {max(scores):.2f}\n")
        log.write(f"AVG SCORE : {sum(scores) / len(scores):.2f}\n")

        log.write("=" * 100 + "\n")

    print(f"\nLog saved to:\n{LOG_FILE}\n")

    assert True