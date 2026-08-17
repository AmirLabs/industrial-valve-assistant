import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from src.tools.pricing.entities import ProductEntities
from src.tools.pricing.product_repository import query_products, get_unique_values, get_available_sizes
from src.preprocess.text_cleaning import get_fallback_suggestion

logger = logging.getLogger(__name__)

# How many times the user may step away from the quote before we let it go.
MAX_DETOURS = 3


class SlotState(str, Enum):
    """Where a pricing conversation currently stands."""
    INACTIVE = "inactive"   # no pricing flow at all
    ACTIVE = "active"       # we asked something and wait for the answer
    PAUSED = "paused"       # flow is alive, but right now we answer another question


@dataclass
class SlotResult:
    status: str                          # "found" | "ask_user" | "not_found"|"give_up"|"suggest_product"
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
        self.state: SlotState = SlotState.INACTIVE         # inactive / active / paused
        self.last_question: Optional[str] = None           # the exact text we showed the user
        self.detour_count: int = 0                         # times the user stepped away from the quote
        self.suggestion: Optional[str] = None              # suggested product name shown to user (Scenario A)
        self.retry_count: int = 0                          # how many times user gave wrong product name

    @property
    def is_active(self) -> bool:
        """
        True while a pricing flow is alive - both while we wait for an answer
        and while it is paused. Read-only: change self.state instead.
        """
        return self.state is not SlotState.INACTIVE

    def start(self, entities: ProductEntities) -> None:
        """Called when pricing flow begins."""
        self.entities = entities
        self.state = SlotState.ACTIVE
        self.waiting_for = None
        self.options = None
        self.fields = []
        self.last_question = None
        self.detour_count = 0

    def remember_question(self, text: str) -> None:
        """
        Stores the question exactly as the user saw it.
        We need this text later to ask it again after a detour, and to tell
        the router what we are waiting for.
        """
        self.last_question = text

    def pause(self) -> None:
        """
        Called when the user asks something else in the middle of the quote.
        Keeps every filled slot - only the state changes.
        """
        if self.state is SlotState.ACTIVE:
            self.state = SlotState.PAUSED
            self.detour_count += 1
            logger.info(
                f"SlotManager [{self.session_id}]: paused "
                f"(detour {self.detour_count}/{MAX_DETOURS})"
            )

    def resume(self) -> None:
        """Called after the other question is answered and we ask ours again."""
        if self.state is SlotState.PAUSED:
            self.state = SlotState.ACTIVE
            logger.info(f"SlotManager [{self.session_id}]: resumed")

    def detour_limit_reached(self) -> bool:
        """True when the user stepped away too many times to keep the quote open."""
        return self.detour_count >= MAX_DETOURS

    def patch(self, value: str) -> None:
        """
        Called when user answers our question.
        Puts the value into the correct slot (waiting_for field).
        """
        if self.waiting_for and self.entities:
            setattr(self.entities, self.waiting_for, value.strip())
            self.waiting_for = None
            self.options = None
            self.last_question = None

    def reset(self) -> None:
        """Called when pricing flow ends (found or not_found)."""
        self.entities = None
        self.fields = []
        self.waiting_for = None
        self.options = None
        self.state = SlotState.INACTIVE
        self.last_question = None
        self.detour_count = 0
        self.suggestion = None
        self.retry_count = 0


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
        # --- Scenario B: product name found but size is wrong for this product ---
        # We know this because inch is already filled (user gave a size)
        # but the combination product+size returns nothing
        if entities.inch is not None:
            available_sizes = get_available_sizes(entities.product_name)
            if available_sizes:
                slot.waiting_for = "inch"
                slot.options = available_sizes
                return SlotResult(
                    status="wrong_size",
                    options=available_sizes,
                    field="inch"
                )
            else:
                # product name itself is wrong — fall through to Scenario A
                pass

        # --- Scenario A: product name not found in database ---
        # Try low threshold fuzzy search to find a suggestion
        MAX_RETRIES = 2
        if slot.retry_count >= MAX_RETRIES:
            slot.reset()
            return SlotResult(status="give_up")

        fallback = get_fallback_suggestion(entities.product_name)
        suggestions = fallback.get("result_of_search", [])

        if suggestions:
            suggested_name = suggestions[0]["product_name"]
            slot.suggestion = suggested_name
            slot.waiting_for = "product_confirmation"
            slot.retry_count += 1
            return SlotResult(
                status="suggest_product",
                field="product_confirmation",
                options=[suggested_name]
            )
        else:
            # No suggestion found at all
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