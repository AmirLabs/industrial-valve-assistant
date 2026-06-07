import pytest
from src.tools.pricing.entities import extract_entities
from src.preprocess.text_cleaning import normalize_to_decimal_inch, normalize_pressure, normalize_brands,search_pipeline


def _extract_and_normalize(user_input: str):
    entities = extract_entities(user_input)
    if entities.product_name:
        result = search_pipeline(entities.product_name)
        matches = result.get('result_of_search', [])
        if matches:
            entities.product_name = matches[0]['product_name']
    if entities.inch:
        entities.inch = normalize_to_decimal_inch(entities.inch)
    if entities.pressur_rating:
        entities.pressur_rating = normalize_pressure(entities.pressur_rating)
    if entities.company:
        entities.company = normalize_brands(entities.company)
    return entities


def test_missing_inch_and_pressure_and_brand():
    entities = _extract_and_normalize("قیمت شیرهای کشویی اتون چنده؟")
    assert entities.product_name == 'شیرفلکه کشویی'
    assert entities.inch is None
    assert entities.pressur_rating is None
    assert entities.company is None


def test_missing_pressure_and_brand():
    entities = _extract_and_normalize("قیمت سوپاپی  ۲ اینچ")
    assert entities.product_name == "شیرسوپاپی"
    assert entities.inch == "2"
    assert entities.pressur_rating is None
    assert entities.company is None


def test_missing_inch():
    entities = _extract_and_normalize("قیمت سوزنی ۱۶ بار کیز چنده")
    assert entities.product_name == "شیرفلکه سوزنی"
    assert entities.inch is None
    assert entities.pressur_rating == "PN16"
    assert entities.company == "کیزایران"


def test_all_entities_extracted():
    entities = _extract_and_normalize("قیمت سوزنی ۳ اینچ pn16 کیز چنده")
    assert entities.product_name == "شیرفلکه سوزنی"
    assert entities.inch == "3"
    assert entities.pressur_rating == "PN16"
    assert entities.company == "کیزایران"