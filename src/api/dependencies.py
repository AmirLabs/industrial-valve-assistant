from src.core.flow_manager import FlowManager

flow_manager = FlowManager()


def get_flow_manager() -> FlowManager:
    return flow_manager