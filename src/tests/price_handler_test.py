import pytest
from unittest.mock import patch, MagicMock
from src.tools.pricing.price_handler import handle_price_query
from src.status.memory import MemoryManager
from src.tools.pricing import price_handler

@pytest.fixture(autouse=True)
def clear_memory():
    """Clear memory before each test to avoid state leakage between tests."""
    price_handler.memory = MemoryManager()


def test_all_entities_extracted_found():
    response = handle_price_query(
        "شیرفلکه کشویی ۲ اینچ PN16 سیم قیمتش چنده؟",
        session_id="session_1"
    )
    assert "38,009,570" in response or "38009570" in response


def test_missing_inch_asks_user():
    response = handle_price_query(
        "قیمت شیر فلکه کشویی",
        session_id="session_2"
    )
    assert "سایز" in response or "اینچ" in response


def test_missing_inch_then_user_answers():
    handle_price_query("قیمت شیر فلکه کشویی", session_id="session_3")
    response = handle_price_query("2", session_id="session_3")
    assert isinstance(response, str)
    assert len(response) > 0


def test_auto_fill_pressure_and_brand():
    response = handle_price_query(
        "قیمت شیرسوپاپی ۱ اینچ",
        session_id="session_4"
    )
    assert "فاراب" in response
    assert "PN16" in response


def test_not_found():
    response = handle_price_query(
        "قیمت شیره مهره ای ۳ اینچ",
        session_id="session_5"
    )
    assert "یافت نشد" in response