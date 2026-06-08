import logging
from src.tools.pricing.entities import extract_entities, ProductEntities
from src.status.slot_manager import SlotManager, SlotResult, check_slots
from src.preprocess.text_cleaning import normalize_to_decimal_inch, normalize_pressure, normalize_brands, search_pipeline

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_entities(entities: ProductEntities) -> None:
    """Normalizes all entity values in-place."""
    if entities.product_name:
        result = search_pipeline(entities.product_name)
        if result["result_of_search"]:
            entities.product_name = result["result_of_search"][0]["product_name"]
    if entities.inch:
        entities.inch = str(normalize_to_decimal_inch(entities.inch))
    if entities.pressur_rating:
        entities.pressur_rating = normalize_pressure(entities.pressur_rating)
    if entities.company:
        entities.company = normalize_brands(entities.company)


def _normalize_single(field: str, value: str) -> str:
    """Normalizes a single value based on which field it belongs to."""
    if field == "inch":
        return str(normalize_to_decimal_inch(value))
    if field == "pressur_rating":
        return normalize_pressure(value)
    if field == "company":
        return normalize_brands(value)
    if field == "product_name":
        return search_pipeline(value)
    return value


def extract_and_normalize(user_input: str) -> ProductEntities:
    """Extracts entities from user input and normalizes all values."""
    entities = extract_entities(user_input)
    _normalize_entities(entities)
    return entities


def _format_price_response(product: dict) -> str:
    return (
        f"محصول: {product['product_name']}\n"
        f"برند: {product['company']}\n"
        f"سایز: {product['inch']} اینچ\n"
        f"فشار کاری: {product['pressur_rating']}\n"
        f"قیمت: {product['price']:,} تومان\n"
    )


def _format_ask_message(result: SlotResult, slot: SlotManager) -> str:
    """Builds a friendly question message based on which field we are asking about."""
    entities = slot.entities
    product = entities.product_name or "محصول"
    inch = entities.inch

    if result.field == "inch":
        return (
            f"برای بررسی قیمت محصول {product} نیاز دارم که سایز هم وارد کنید، "
            f"سایز مورد نظرتون چیست؟"
        )

    if result.field == "pressur_rating":
        options_text = " و ".join(result.options) if result.options else ""
        return (
            f"محصول {product} با سایز {inch} اینچ "
            f"دارای دو نوع فشار {options_text} هست، "
            f"کدام یک مد نظر شماست؟"
        )

    if result.field == "company":
        options_text = " و ".join(result.options) if result.options else ""
        pressure_part = (
            f"با فشار کاری {entities.pressur_rating} "
            if entities.pressur_rating else ""
        )
        return (
            f"محصول {product} با سایز {inch} اینچ "
            f"{pressure_part}"
            f"برندهای {options_text} موجوده، "
            f"کدام یک مد نظر شماست؟"
        )

    # fallback — should not normally happen
    return result.question


# ---------------------------------------------------------------------------
# Main handler
# ---------------------------------------------------------------------------

def handle_price_query(user_input: str, slot: SlotManager) -> str:
    """
    Handles one turn of a pricing conversation.

    Two cases:
    1. slot.waiting_for is set  → user answering our question → normalize then patch
    2. slot.waiting_for is None → fresh input → extract, normalize, then start
    """
    print(f"DEBUG slot state: waiting_for={slot.waiting_for}, is_active={slot.is_active}")
    print(f"DEBUG user_input: {user_input}")
    try:
        # --- Case 1: user is answering our question ---
        if slot.waiting_for:
            normalized = _normalize_single(slot.waiting_for, user_input)
            slot.patch(normalized)

        # --- Case 2: fresh start ---
        else:
            entities = extract_and_normalize(user_input)
            slot.start(entities)
            print(f"DEBUG entities: {slot.entities.model_dump()}")

        # --- Run slot check and decide next action ---
        result: SlotResult = check_slots(slot)

        if result.status == "not_found":
            return "محصول مورد نظر شما در سیستم یافت نشد. لطفاً مشخصات دیگری را امتحان کنید."

        if result.status == "ask_user":
            return _format_ask_message(result, slot)

        if result.status == "found":
            return _format_price_response(result.product)

    except Exception as e:
        logger.error(f"price_handler failed: {e}", exc_info=True)
        slot.reset()
        return "مشکلی در پردازش درخواست قیمت به وجود آمده است."