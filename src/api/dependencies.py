from src.core.flow_manager import FlowManager
from src.database.conversation_engine import get_db_session  # noqa: F401  (re-exported for use in chat.py)

flow_manager = FlowManager()


def get_flow_manager() -> FlowManager:
    return flow_manager