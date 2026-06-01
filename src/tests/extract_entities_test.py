from src.tools.pricing.entities import extract_entities
from src.preprocess.text_cleaning import normalize_to_decimal_inch, normalize_pressure, normalize_brands

scenarios = [
    "شیرفلکه کشویی ۲ اینچ PN16 سیم قیمتش چنده؟",
    "قیمت شیرسوپاپی ۱ اینچ",
]

for s in scenarios:
    result = extract_entities(s)
    
    inch = str(normalize_to_decimal_inch(result.inch)) if result.inch else None
    pressure = normalize_pressure(result.pressur_rating) if result.pressur_rating else None
    company = normalize_brands(result.company) if result.company else None
    
    print(f"Input: {s}")
    print(f"inch normalized          : {inch}")
    print(f"pressur_rating normalized: {pressure}")
    print(f"company normalized       : {company}")
    print("---")