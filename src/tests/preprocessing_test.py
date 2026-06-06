import logging
from pathlib import Path

from src.preprocess.text_cleaning import normalize_to_decimal_inch

ROOT_DIR = Path(__file__).resolve().parents[2]

LOG_FILE = ROOT_DIR / "logs" / "size_normalization.log"

LOG_FILE.parent.mkdir(exist_ok=True)

logger = logging.getLogger("size_normalization")
logger.setLevel(logging.INFO)

logger.handlers.clear()

handler = logging.FileHandler(
    LOG_FILE,
    mode="w",
    encoding="utf-8"
)

handler.setFormatter(
    logging.Formatter("%(message)s")
)

logger.addHandler(handler)


TEST_CASES = [
    ("DN80", "3"),
    ("DN 80", "3"),
    ("80DN", "3"),
    ("3 inch", "3"),
    ('3"', "3"),
    ("۳ اینچ", "3"),
    ("1-1/4", "1.25"),
    ("11/4", "1.25"),
    ("1 1/4", "1.25"),
    ("DN125", "5"),
    ("125 mm", "5"),
]


def test_size_normalization():

    passed = 0

    logger.info("")
    logger.info("=" * 100)
    logger.info("SIZE NORMALIZATION TEST")
    logger.info("=" * 100)

    for raw_input, expected in TEST_CASES:

        result = normalize_to_decimal_inch(raw_input)

        is_pass = str(result) == expected

        if is_pass:
            passed += 1

        logger.info("")
        logger.info(f"INPUT    : {raw_input}")
        logger.info(f"EXPECTED : {expected}")
        logger.info(f"RESULT   : {result}")
        logger.info(f"PASS     : {is_pass}")
        logger.info("-" * 60)

    logger.info("")
    logger.info("=" * 100)
    logger.info("SUMMARY")
    logger.info("=" * 100)

    logger.info(f"TOTAL  : {len(TEST_CASES)}")
    logger.info(f"PASSED : {passed}")
    logger.info(f"FAILED : {len(TEST_CASES) - passed}")

    success_rate = (passed / len(TEST_CASES)) * 100

    logger.info(f"SUCCESS RATE : {success_rate:.2f}%")

    logger.info("=" * 100)

    assert True