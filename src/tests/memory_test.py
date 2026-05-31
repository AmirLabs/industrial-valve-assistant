import pytest
from unittest.mock import patch, MagicMock
from src.states.memory import MemoryManager
from src.core.flow_manager import FlowManager


# --- MemoryManager Tests ---

def test_memory_add_and_get():
    memory = MemoryManager(window_size=8)
    memory.add_message("session_1", "user", "hello")
    memory.add_message("session_1", "assistant", "hi there")

    history = memory.get_history("session_1")
    assert len(history) == 2
    assert history[0] == {"role": "user", "content": "hello"}
    assert history[1] == {"role": "assistant", "content": "hi there"}


def test_memory_window_size():
    memory = MemoryManager(window_size=3)
    for i in range(6):
        memory.add_message("session_1", "user", f"message {i}")

    history = memory.get_history("session_1")
    assert len(history) == 3
    assert history[-1]["content"] == "message 5"


def test_memory_session_isolation():
    memory = MemoryManager()
    memory.add_message("session_1", "user", "hello from s1")
    memory.add_message("session_2", "user", "hello from s2")

    assert len(memory.get_history("session_1")) == 1
    assert len(memory.get_history("session_2")) == 1


def test_memory_clear():
    memory = MemoryManager()
    memory.add_message("session_1", "user", "hello")
    memory.clear_history("session_1")

    assert memory.get_history("session_1") == []


def test_memory_empty_session():
    memory = MemoryManager()
    assert memory.get_history("nonexistent") == []


# --- FlowManager Tests ---

@patch("src.core.flow_manager.handle_general_query", return_value="general response")
@patch("src.core.flow_manager.get_chat_response", return_value="faq response")
def test_flow_saves_messages_to_memory(mock_faq, mock_general):
    flow = FlowManager()

    mock_intent = MagicMock()
    mock_intent.intent = "general"
    flow.router.route_message = MagicMock(return_value=mock_intent)

    flow.process_message("what is this?", session_id="session_1")

    history = flow.memory.get_history("session_1")
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"


@patch("src.core.flow_manager.handle_general_query", return_value="general response")
def test_flow_routes_general_intent(mock_general):
    flow = FlowManager()

    mock_intent = MagicMock()
    mock_intent.intent = "general"
    flow.router.route_message = MagicMock(return_value=mock_intent)

    response = flow.process_message("tell me about valves", session_id="session_1")
    assert response == "general response"
    mock_general.assert_called_once()


@patch("src.core.flow_manager.get_chat_response", return_value="faq response")
def test_flow_routes_faq_intent(mock_faq):
    flow = FlowManager()

    mock_intent = MagicMock()
    mock_intent.intent = "faq"
    flow.router.route_message = MagicMock(return_value=mock_intent)

    response = flow.process_message("what are your working hours?", session_id="session_1")
    assert response == "faq response"
    mock_faq.assert_called_once()


@patch("src.core.flow_manager.get_chat_response", return_value=None)
def test_flow_faq_fallback_message(mock_faq):
    flow = FlowManager()

    mock_intent = MagicMock()
    mock_intent.intent = "faq"
    flow.router.route_message = MagicMock(return_value=mock_intent)

    response = flow.process_message("some unknown question", session_id="session_1")
    assert response != ""
    assert isinstance(response, str)


def test_flow_empty_message():
    flow = FlowManager()
    response = flow.process_message("   ", session_id="session_1")
    assert response == "لطفاً پیام خود را به صورت متنی بنویسید."


def test_flow_unknown_intent():
    flow = FlowManager()

    mock_intent = MagicMock()
    mock_intent.intent = "product_search"
    flow.router.route_message = MagicMock(return_value=mock_intent)

    response = flow.process_message("I want to buy a valve", session_id="session_1")
    assert isinstance(response, str)


@patch("src.core.flow_manager.get_chat_response")
def test_flow_history_passed_to_faq_tool(mock_faq):
    mock_faq.return_value = "response"
    flow = FlowManager()

    mock_intent = MagicMock()
    mock_intent.intent = "faq"
    flow.router.route_message = MagicMock(return_value=mock_intent)

    flow.process_message("first message", session_id="session_1")
    flow.process_message("second message", session_id="session_1")

    _, kwargs = mock_faq.call_args
    assert "history" in kwargs
    assert len(kwargs["history"]) >= 2


@patch("src.tools.faq.retriever.handle_llm_fallback")
def test_faq_passes_history_to_llm_fallback(mock_fallback):
    mock_fallback.return_value = "llm response"

    from src.tools.faq.retriever import get_chat_response

    history = [
        {"role": "user", "content": "قیمت شیر فلکه میراب چنده؟"},
        {"role": "assistant", "content": "قیمت ۲ اینچ ۵۰۰ هزار تومانه"},
    ]

    get_chat_response("xyzzy gibberish 99999", history=history)

    mock_fallback.assert_called_once_with("xyzzy gibberish 99999", history=history)