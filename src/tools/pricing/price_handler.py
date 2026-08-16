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


CONFIRMATION_WORDS = {
    "بله", "آره", "آری", "درسته", "بلی", "yes", "y",
    "همینه", "همینو", "همین", "دقیقا", "اره", "اوکی", "ok", "اوک"
}


def _is_confirmation(user_input: str) -> bool:
    """Checks if the user's response is a confirmation (yes) or not (no / new input)."""
    cleaned = user_input.strip().lower()
    return cleaned in CONFIRMATION_WORDS


def extract_and_normalize(user_input: str) -> ProductEntities:
    """Extracts entities from user input and normalizes all values."""
    entities = extract_entities(user_input)
    _normalize_entities(entities)
    return entities


def _format_suggest_product_message(original: str, suggested: str) -> str:
    """Builds a confirmation message when we suggest a corrected product name."""
    return (
        f"محصولی با نام «{original}» در سیستم پیدا نکردم، "
        f"اما محصولی داریم به اسم «{suggested}». "
        f"منظورتون همین محصول بود؟"
    )


def _format_wrong_size_message(product: str, available_sizes: list) -> str:
    """Builds a message when the size user gave does not exist for this product."""
    sizes_text = "، ".join(available_sizes)
    return (
        f"سایزی که وارد کردید برای «{product}» در سیستم موجود نیست.\n"
        f"سایزهای موجود برای این محصول:\n"
        f"{sizes_text} اینچ\n"
        f"کدومش مد نظرته؟"
    )


def _format_price_response(product: dict) -> str:
    return (
        f"محصول: {product['product_name']}\n"
        f"برند: {product['company']}\n"
        f"سایز: {product['inch']} اینچ\n"
        f"فشار کاری: {product['pressur_rating']}\n"
        f"قیمت: {product['price']} ریال\n"
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

def handle_price_query(user_input: str, slot: SlotManager, trace=None) -> str:
    """
    Handles one turn of a pricing conversation.

    Three cases:
    1. slot.waiting_for == "product_confirmation" → user answering our product suggestion
    2. slot.waiting_for is set (other fields)     → user answering our question → patch
    3. slot.waiting_for is None                   → fresh input → extract, normalize, start
    """
    print(f"DEBUG slot state: waiting_for={slot.waiting_for}, is_active={slot.is_active}")
    print(f"DEBUG user_input: {user_input}")
    try:
        # --- Case 1: user is confirming or rejecting our product suggestion ---
        if slot.waiting_for == "product_confirmation":
            confirmed = _is_confirmation(user_input)

            if confirmed:
                # User said yes → patch product_name with our suggestion and continue
                slot.entities.product_name = slot.suggestion
                slot.suggestion = None
                slot.waiting_for = None

            else:
                # User said no or gave a new wrong name → try again with new input
                # Extract product name from new input if user typed something new
                # Otherwise use raw input as the new product name attempt
                new_entities = extract_and_normalize(user_input)
                new_product = new_entities.product_name or user_input
                slot.entities.product_name = new_product
                slot.suggestion = None
                slot.waiting_for = None

        # --- Case 2: user is answering our question (size, pressure, brand) ---
        elif slot.waiting_for:
            normalized = _normalize_single(slot.waiting_for, user_input)
            slot.patch(normalized)

        # --- Case 3: fresh start ---
        else:
            entities = extract_and_normalize(user_input)
            slot.start(entities)
            print(f"DEBUG entities: {slot.entities.model_dump()}")

        # --- Run slot check and decide next action ---
        result: SlotResult = check_slots(slot)

        if trace:
            # Snapshot what we know at the end of this pricing turn.
            try:
                trace.entities = slot.entities.model_dump()
            except Exception:
                trace.entities = None
            trace.slot_status = result.status
            trace.waiting_for = slot.waiting_for
            trace.options = result.options

        if result.status == "not_found":
            return "محصول مورد نظر شما در سیستم یافت نشد. لطفاً مشخصات دیگری را امتحان کنید."

        if result.status == "give_up":
            return (
                "متاسفانه بعد از چند بار تلاش نتونستم محصول مورد نظرتون رو پیدا کنم.\n"
                "لطفاً با پشتیبانی تماس بگیرید یا محصول رو از سایت انتخاب کنید."
            )

        if result.status == "suggest_product":
            original = slot.entities.product_name
            suggested = slot.suggestion
            return _format_suggest_product_message(original, suggested)

        if result.status == "wrong_size":
            product = slot.entities.product_name or "این محصول"
            return _format_wrong_size_message(product, result.options)

        if result.status == "ask_user":
            return _format_ask_message(result, slot)

        if result.status == "found":
            return _format_price_response(result.product)

    except Exception as e:
        logger.error(f"price_handler failed: {e}", exc_info=True)
        slot.reset()
        return "مشکلی در پردازش درخواست قیمت به وجود آمده است."