import pytest
from pydantic import ValidationError

from app.schemas.chat import ChatMessage, ChatRequest, ChatResponse, Recommendation


def test_chat_message_rejects_invalid_role():
    with pytest.raises(ValidationError):
        ChatMessage(role="system", content="hi")


def test_chat_request_rejects_empty_messages():
    with pytest.raises(ValidationError):
        ChatRequest(messages=[])


def test_chat_response_defaults_match_spec():
    resp = ChatResponse(reply="hello")
    assert resp.recommendations == []
    assert resp.end_of_conversation is False


def test_chat_response_rejects_more_than_ten_recommendations():
    recs = [Recommendation(name=f"Test {i}", url="https://www.shl.com/x", test_type="K") for i in range(11)]
    with pytest.raises(ValidationError):
        ChatResponse(reply="too many", recommendations=recs)


def test_chat_response_serializes_to_exact_keys():
    resp = ChatResponse(
        reply="Got it.",
        recommendations=[Recommendation(name="SQL (New)", url="https://www.shl.com/x", test_type="K")],
        end_of_conversation=False,
    )
    data = resp.model_dump()
    assert set(data.keys()) == {"reply", "recommendations", "end_of_conversation"}
    assert set(data["recommendations"][0].keys()) == {"name", "url", "test_type"}
