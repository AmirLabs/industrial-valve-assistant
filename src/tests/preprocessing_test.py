import pytest
import os
import json
from unittest.mock import patch, mock_open
# Assuming your main code file is named 'preprocessing.py'
from src.preprocess.text_cleaning import clean_text, normalize_to_decimal_inch, normalize_pressure, normalize_brands, search_pipeline

# --- 1. Size Normalization Tests ---

def test_normalize_to_decimal_inch_sticky_fraction():
    """Verify handling of sticky fractions without separators like '11/2'."""
    assert normalize_to_decimal_inch("11/2") == 1.5


def test_normalize_to_decimal_inch_standard_fraction():
    """Verify standard fraction parsing like '3/4'."""
    assert normalize_to_decimal_inch("3/4") == 0.75


# --- 2. Pressure Normalization Tests ---

def test_normalize_pressure_persian_unit():
    """Verify pressure normalization with Persian characters and digits."""
    assert normalize_pressure("۱۶ بار") == "PN16"


def test_normalize_pressure_persian_class():
    """Verify pressure normalization with Persian 'کلاس' and sticky text."""
    assert normalize_pressure("کلاس۱۵۰") == "CL150"


def test_normalize_pressure_standard_pn():
    """Verify standard lowercase/uppercase PN parsing."""
    assert normalize_pressure("pn16") == "PN16"


def test_normalize_pressure_standard_class():
    """Verify standard lowercase/uppercase Class parsing with space removal."""
    assert normalize_pressure("class150") == "CL150"


# --- 3. Brand Normalization Tests ---

# We mock the built-in open and os.path.exists to simulate the exact JSON data for brands
@patch("os.path.exists", return_value=True)
@patch("builtins.open", new_callable=mock_open, read_data=json.dumps({
    "سیم ایتالیا": "سیم",
    "میراپ": "میراب"
}))
def test_normalize_brands_mappings(mock_file, mock_exists):
    """Test brand mappings for specialized market names using mocked config."""
    assert normalize_brands("سیم ایتالیا") == "سیم"
    assert normalize_brands("میراپ") == "میراب"


# --- 4. Search Pipeline (End-to-End) Tests ---

# Mocking the JSON configuration and the global products_list for pipeline execution
# --- 4. Search Pipeline (End-to-End) Tests ---

@patch("src.preprocess.text_cleaning.products_list", [
    "شیرسوپاپی مخصوص بخار",  # Updated to match your exact production data structure
    "شیرسوپاپی", 
    "شیر فلکه کشویی"
])
@patch("os.path.exists", return_value=True)
@patch("builtins.open", new_callable=mock_open, read_data=json.dumps({
    "بشقابی بخار": "شیرسوپاپی مخصوص بخار",
    "سورنی": "شیر سوزنی"
}))
def test_search_pipeline_complex_queries(mock_file, mock_exists):
    """Test pipeline robustness against combined typos and slang using production-like data."""
    result_1 = search_pipeline("بشغابی بخار")
    assert isinstance(result_1, dict)
    assert len(result_1["result_of_search"]) > 0
    # Now it will perfectly match with score 100.0
    assert result_1["result_of_search"][0]["product_name"] == "شیرسوپاپی مخصوص بخار"