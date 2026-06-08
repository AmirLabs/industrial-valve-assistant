import logging
from dataclasses import dataclass, field
from typing import Optional
from src.tools.pricing.entities import ProductEntities
from src.tools.pricing.product_repository import query_products, get_unique_values

logger = logging.getLogger(__name__)

@dataclass
class SlotResult:
    status: str                          # "found" | "ask_user" | "not_found"
    product: Optional[dict] = None       # final product row when found
    question: Optional[str] = None       # question to ask user
    options: Optional[list] = None       # choices from database
    field: Optional[str] = None          # which parameter we are waiting for

class SlotManager:
    """
    Holds the full state of an in-progress pricing conversation.
    One instance per session_id, stored in FlowManager.
    """

    def __init__(self, session_id: str):
        self.session_id: str = session_id
        self.entities: Optional[ProductEntities] = None   # extracted from user message
        self.fields: list[str] = []                        # all parameters still missing
        self.waiting_for: Optional[str] = None             # parameter we asked about RIGHT NOW
        self.options: Optional[list] = None                # choices shown to user
        self.is_active: bool = False                       # True = inside pricing flow

    def start(self, entities: ProductEntities) -> None:
        """Called when pricing flow begins."""
        self.entities = entities
        self.is_active = True
        self.waiting_for = None
        self.options = None
        self.fields = []

    def patch(self, value: str) -> None:
        """
        Called when user answers our question.
        Puts the value into the correct slot (waiting_for field).
        """
        if self.waiting_for and self.entities:
            setattr(self.entities, self.waiting_for, value.strip())
            self.waiting_for = None
            self.options = None

    def reset(self) -> None:
        """Called when pricing flow ends (found or not_found)."""
        self.entities = None
        self.fields = []
        self.waiting_for = None
        self.options = None
        self.is_active = False


def check_slots(slot: SlotManager) -> SlotResult:
    """
    Evaluates the current slot state and returns what to do next.

    Order of operations (as designed):
    1. Check required fields (product_name, inch)
    2. Query database with what we have
    3. Check if pressure_rating is needed
    4. Check if company is needed
    5. Return found if single result remains
    """
    entities = slot.entities

    # --- Step 1: check required fields ---
    missing = entities.missing_required()
    if missing:
        field = missing[0]
        slot.waiting_for = field
        slot.fields = missing

        questions = {
            "product_name": "لطفاً نام محصول مورد نظر خود را وارد کنید.",
            "inch": "لطفاً سایز محصول را وارد کنید."
        }
        return SlotResult(
            status="ask_user",
            question=questions[field],
            field=field
        )

    # --- Step 2: query database ---
    results = query_products(entities)

    if not results:
        slot.reset()
        return SlotResult(status="not_found")

    if len(results) == 1:
        slot.reset()
        return SlotResult(status="found", product=results[0])

    # --- Step 3: check pressure_rating ---
    if entities.pressur_rating is None:
        unique_pressures = get_unique_values(entities, "pressur_rating")
        if len(unique_pressures) == 1:
            entities.pressur_rating = unique_pressures[0]
            return check_slots(slot)  # re-run with auto-filled value
        elif len(unique_pressures) > 1:
            slot.waiting_for = "pressur_rating"
            slot.options = unique_pressures
            slot.fields = ["pressur_rating"]
            return SlotResult(
                status="ask_user",
                question="فشار کاری مورد نظر شما کدام است؟",
                options=unique_pressures,
                field="pressur_rating"
            )

    # --- Step 4: check company ---
    if entities.company is None:
        unique_companies = get_unique_values(entities, "company")
        if len(unique_companies) == 1:
            entities.company = unique_companies[0]
            return check_slots(slot)  # re-run with auto-filled value
        elif len(unique_companies) > 1:
            slot.waiting_for = "company"
            slot.options = unique_companies
            slot.fields = ["company"]
            return SlotResult(
                status="ask_user",
                question="برند مورد نظر شما کدام است؟",
                options=unique_companies,
                field="company"
            )

    # --- Step 5: return best match ---
    slot.reset()
    return SlotResult(status="found", product=results[0])
    
 