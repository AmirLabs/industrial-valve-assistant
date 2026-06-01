import logging
from dataclasses import dataclass
from typing import Optional
from src.tools.pricing.entities import ProductEntities
from src.tools.pricing.product_repository import query_products, get_unique_values

logger = logging.getLogger(__name__)


@dataclass
class SlotResult:
    status: str  # "found" | "ask_user" | "not_found"
    product: Optional[dict] = None
    question: Optional[str] = None
    options: Optional[list] = None
    field: Optional[str] = None


def check_slots(entities: ProductEntities) -> SlotResult:
    missing = entities.missing_required()
    if missing:
        field = missing[0]
        questions = {
            "product_name": "لطفاً نام محصول مورد نظر خود را وارد کنید.",
            "inch": "لطفاً سایز محصول را وارد کنید."
        }
        return SlotResult(
            status="ask_user",
            question=questions[field],
            field=field
        )

    results = query_products(entities)

    if not results:
        return SlotResult(status="not_found")

    if len(results) == 1:
        return SlotResult(status="found", product=results[0])

    if entities.pressur_rating is None:
        unique_pressures = get_unique_values(entities, "pressur_rating")
        if len(unique_pressures) == 1:
            entities.pressur_rating = unique_pressures[0]
            return check_slots(entities)
        elif len(unique_pressures) > 1:
            return SlotResult(
                status="ask_user",
                question="فشار کاری مورد نظر شما کدام است؟",
                options=unique_pressures,
                field="pressur_rating"
            )

    if entities.company is None:
        unique_companies = get_unique_values(entities, "company")
        if len(unique_companies) == 1:
            entities.company = unique_companies[0]
            return check_slots(entities)
        elif len(unique_companies) > 1:
            return SlotResult(
                status="ask_user",
                question="برند مورد نظر شما کدام است؟",
                options=unique_companies,
                field="company"
            )

    return SlotResult(status="found", product=results[0])