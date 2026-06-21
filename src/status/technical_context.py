from typing import Optional


class TechnicalContext:
    """
    Holds per-session state for technical intent.
    One instance per session_id, stored in FlowManager —
    same pattern as SlotManager for pricing.

    Used to resolve follow-up questions like:
    "همینو میشه برای آب گرم هم استفاده کرد؟"
    by remembering the last product resolved in this session.
    """

    def __init__(self, session_id: str):
        self.session_id: str = session_id
        self.last_product: Optional[dict] = None  # metadata of last resolved product

    def remember_product(self, metadata: dict) -> None:
        """Called after a successful answer to save product context."""
        self.last_product = metadata

    def reset(self) -> None:
        """Clears remembered product (e.g. if conversation topic changes)."""
        self.last_product = None