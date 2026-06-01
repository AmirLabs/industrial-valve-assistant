import json
import logging
from src.status.memory import MemoryManager
from src.tools.pricing.entities import extract_entities, ProductEntities
from src.status.slot_manager import check_slots, SlotResult
from src.preprocess.text_cleaning import normalize_to_decimal_inch, normalize_pressure, normalize_brands

logger = logging.getLogger(__name__)

memory = MemoryManager()


def _save_entities(session_id: str, entities: ProductEntities) -> None:
    memory.add_message(session_id, "entities", json.dumps(entities.model_dump()))


def _load_entities(session_id: str) -> ProductEntities | None:
    history = memory.get_history(session_id)
    entities_msg = next((m for m in reversed(history) if m["role"] == "entities"), None)
    if entities_msg:
        return ProductEntities(**json.loads(entities_msg["content"]))
    return None


def _clear_entities(session_id: str) -> None:
    memory.clear_history(session_id)


def _normalize_entities(entities: ProductEntities) -> ProductEntities:
    if entities.inch:
        entities.inch = str(normalize_to_decimal_inch(entities.inch))
    if entities.pressur_rating:
        entities.pressur_rating = normalize_pressure(entities.pressur_rating)
    if entities.company:
        entities.company = normalize_brands(entities.company)
    return entities


def _format_price_response(product: dict) -> str:
    return (
        f"محصول: {product['product_name']}\n"
        f"برند: {product['company']}\n"
        f"سایز: {product['inch']} اینچ\n"
        f"فشار کاری: {product['pressur_rating']}\n"
        f"قیمت: {product['price']:,} تومان\n"
        f"موجودی: {product['stock']} عدد"
    )


def handle_price_query(user_input: str, session_id: str) -> str:
    try:
        existing_entities = _load_entities(session_id)

        if existing_entities:
            field = next(
                (m["content"] for m in reversed(memory.get_history(session_id))
                 if m["role"] == "waiting_for"), None
            )
            if field:
                setattr(existing_entities, field, user_input.strip())
                existing_entities = _normalize_entities(existing_entities)
            entities = existing_entities
        else:
            entities = extract_entities(user_input)
            entities = _normalize_entities(entities)

        result: SlotResult = check_slots(entities)

        if result.status == "not_found":
            _clear_entities(session_id)
            return "محصول مورد نظر شما در سیستم یافت نشد. لطفاً مشخصات دیگری را امتحان کنید."

        if result.status == "ask_user":
            _save_entities(session_id, entities)
            memory.add_message(session_id, "waiting_for", result.field)
            if result.options:
                options_text = "، ".join(result.options)
                return f"{result.question}\nگزینه‌ها: {options_text}"
            return result.question

        if result.status == "found":
            _clear_entities(session_id)
            return _format_price_response(result.product)

    except Exception as e:
        logger.error(f"price_handler failed: {e}")
        return "مشکلی در پردازش درخواست قیمت به وجود آمده است."