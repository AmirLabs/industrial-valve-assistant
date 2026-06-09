import os
import re
import json
import pandas as pd
from src.config.setting import settings
from rapidfuzz import process, fuzz
from src.data.products import products_list

# Global path configuration derived from centralized settings
SYNONYMS_JSON_PATH = settings.ALIAS_PATH


def clean_text(text: str) -> str:
    """Normalizes Arabic/Persian characters, digits, and removes hidden unicode markers.

    Args:
        text: The raw input string from the user.

    Returns:
        A thoroughly cleaned and stripped string.
    """
    if not isinstance(text, str):
        return text
    
    # Remove hidden directional formatting characters
    text = re.sub(r'[\u200b-\u200f\u202a-\u202e]', '', text)    
    # Convert Persian/Arabic digits to standard English digits
    fa_to_en = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    text = text.translate(fa_to_en)

    # Standardize specific character variations
    text = text.replace("ي", "ی").replace("ك", "ک")
    
    # Collapse multiple whitespace characters into a single space
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()


def get_similar_products(user_input: str,threshold: int = 70) -> dict:
    """Product search with exact-match priority."""

    if not user_input or not products_list:
        return {
            "result_of_search": [],
            "Flag": False
        }

    cleaned_input = clean_text(user_input)

    exact_matches = []

    for product in products_list:
        if clean_text(product) == cleaned_input:
            exact_matches.append({
                "product_name": product,
                "score": 100.0
            })

    if exact_matches:

        return {
            "result_of_search": exact_matches,
            "Flag": False
            }

    matches = process.extract(
        cleaned_input,
        products_list,
        scorer=fuzz.token_set_ratio,
        score_cutoff=threshold,
        limit=None)

    all_results = [{"product_name": match[0],"score": round(match[1], 2)}for match in matches]

    if not all_results:

        return {
            "result_of_search": [],
            "Flag": False
        }
    max_score = max(item["score"]for item in all_results)

    filtered_results = [
        item for item in all_results if (max_score - item["score"]) <= 10
    ]

    red_flag = len(filtered_results) > 1

    return {
        "result_of_search": filtered_results,
        "Flag": red_flag
    }

def resolve_alias_fuzzy(user_input: str, threshold: int = 75) -> str:
    """Resolves slang or typos in market terms using fuzzy matching against an alias map.

    Args:
        user_input: The raw or cleaned input string from the user.
        threshold: The minimum similarity score to accept an alias match.

    Returns:
        The standardized product term if a match is found; otherwise, the original input.
    """
    if not user_input or not os.path.exists(SYNONYMS_JSON_PATH):
        return user_input

    try:
        with open(SYNONYMS_JSON_PATH, "r", encoding="utf-8") as f:
            synonyms_dict = json.load(f)
            
        if not synonyms_dict:
            return user_input
            
        cleaned_input = clean_text(user_input)
        alias_keys = list(synonyms_dict.keys())
        
        # Perform fuzzy matching on the keys of the alias dictionary
        best_match = process.extractOne(
            cleaned_input, 
            alias_keys, 
            scorer=fuzz.QRatio
        )
        
        # If the match is strong enough, return its standardized value
        if best_match and best_match[1] >= threshold:
            matched_key = best_match[0]
            return synonyms_dict[matched_key]

    except Exception as e:
        # Fallback to original input in case of any unexpected I/O or JSON errors
        print(f"Error in alias resolution: {e}")
        
    return user_input


def search_pipeline(user_input: str) -> dict:
    """Orchestrates the search pipeline by resolving aliases before matching products.

    Args:
        user_input: The raw query from the user.

    Returns:
        A dictionary containing the final product search results and status flags.
    """
    # Step 1: Resolve typos or market jargon via the fuzzy alias layer
    resolved_input = resolve_alias_fuzzy(user_input, threshold=75)
    
    # Step 2: Feed the standardized term into the main product search engine
    search_result = get_similar_products(resolved_input, threshold=65)
    
    return search_result


def normalize_pressure(pressure_input: str) -> str:
    """Normalizes industrial valve pressure ratings into standard formats (PN or CL).

    Args:
        pressure_input: The raw pressure input string (e.g., '16 بار', 'class 150').

    Returns:
        A standardized string representation of the pressure rating, or the cleaned string.
    """
    if not pressure_input:
        return None
        
    pressure_clean = clean_text(pressure_input)
    pressure_clean = pressure_clean.strip().upper().replace(" ", "")
    
    # Remove common local/global suffixes
    pressure_clean = pressure_clean.replace("بار", "").replace("BAR", "")
    
    # Standardize class naming variants to 'CL'
    pressure_clean = pressure_clean.replace("کلاس", "CL").replace("LBS", "CL").replace("#", "CL").replace('CLASS', "CL")
    
    if "CL" in pressure_clean and not pressure_clean.startswith("CLASS"):
        pressure_clean = f"CL{pressure_clean.replace('CL', '')}"

    # Return validated standard outputs
    if pressure_clean.startswith("PN") or pressure_clean.startswith("CL"):
        return pressure_clean
    
    if pressure_clean.isdigit():
        return f"PN{pressure_clean}"
    
    return pressure_clean


def normalize_to_decimal_inch(input_size):
    mm_to_inch_decimal = {
        "8": 0.25,
        "10": 0.375,
        "15": 0.5,
        "20": 0.75,
        "25": 1.0,
        "32": 1.25,
        "40": 1.5,
        "50": 2.0,
        "65": 2.5,
        "80": 3.0,
        "100": 4.0,
        "125": 5.0,
        "150": 6.0,
        "200": 8.0,
        "250": 10.0,
        "300": 12.0,
    }

    def _to_clean_str(value):
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)

    clean_input = clean_text(str(input_size)).lower()
    clean_input = (
        clean_input
        .replace('"', '')
        .replace('inch', '')
        .replace('in', '')
        .replace('اینچ', '')
        .strip()
    )

    if "mm" in clean_input or "dn" in clean_input:
        val_mm = re.sub(r'[^0-9]', '', clean_input)
        result = mm_to_inch_decimal.get(val_mm, f"Unknown DN {val_mm}")
        return _to_clean_str(result) if isinstance(result, float) else result

    if '/' not in clean_input:
        try:
            if float(clean_input) >= 8:
                val_mm = str(int(float(clean_input)))
                result = mm_to_inch_decimal.get(val_mm, f"Unknown DN {val_mm}")
                return _to_clean_str(result) if isinstance(result, float) else result
        except ValueError:
            pass

    space_fraction = re.match(r'^(\d+)\s+(\d+)/(\d+)$', clean_input)
    if space_fraction:
        whole = float(space_fraction.group(1))
        num = float(space_fraction.group(2))
        denom = float(space_fraction.group(3))
        return _to_clean_str(whole + (num / denom))

    triple_fraction = re.match(r'^(\d+)/(\d+)/(\d+)$', clean_input)
    if triple_fraction:
        whole = float(triple_fraction.group(1))
        num = float(triple_fraction.group(2))
        denom = float(triple_fraction.group(3))
        return _to_clean_str(whole + (num / denom))

    sticky_fraction = re.match(r'^(\d)(\d)/(\d+)$', clean_input)
    if sticky_fraction:
        whole = float(sticky_fraction.group(1))
        num = float(sticky_fraction.group(2))
        denom = float(sticky_fraction.group(3))
        return _to_clean_str(whole + (num / denom))

    if '-' in clean_input:
        parts = clean_input.split('-')
        if len(parts) == 2 and '/' in parts[1]:
            whole = float(parts[0])
            num, denom = map(float, parts[1].split('/'))
            return _to_clean_str(whole + (num / denom))

    if '/' in clean_input:
        num, denom = map(float, clean_input.split('/'))
        return _to_clean_str(num / denom)

    try:
        return _to_clean_str(float(clean_input))
    except ValueError:
        return clean_input

def get_fallback_suggestion(user_input: str, threshold: int = 25) -> dict:
    """Last-resort fuzzy search with a very low threshold for wrong product names.

    This is only called when search_pipeline() returns empty (normal threshold failed).
    It tries to find the nearest product even with a low similarity score,
    so we can suggest it to the user and ask them to confirm.

    Args:
        user_input: The wrong product name from the user.
        threshold: Very low threshold (default 25) to catch even distant matches.

    Returns:
        A dict with "result_of_search" list and "Flag" bool — same format as get_similar_products().
    """
    resolved_input = resolve_alias_fuzzy(user_input, threshold=75)
    return get_similar_products(resolved_input, threshold=threshold)


def normalize_brands(input_text: str) -> str:
    """Retrieves the exact matching company brand equivalent from the configuration map.

    Args:
        input_text: The user-provided brand query.

    Returns:
        The matched standardized brand name or the original input if not found.
    """
    cleaned_text = clean_text(input_text)
    
    if not os.path.exists(SYNONYMS_JSON_PATH):
        raise FileNotFoundError(f"file does not exist check the path")
        
    with open(SYNONYMS_JSON_PATH, 'r', encoding='utf-8') as file:
        try:
            mapping_data = json.load(file)
        except json.JSONDecodeError:
            raise ValueError("The file does not support Json format Check the format")
            
    equivalent = mapping_data.get(cleaned_text, cleaned_text)
    
    return equivalent