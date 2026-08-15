from research_ingestion.classify import ZeroCostOmniRoute, deterministic_classify
from research_ingestion.models import Candidate
import httpx


def candidate(title: str, abstract: str = "") -> Candidate:
    return Candidate(source="test", title=title, abstract=abstract, canonical_url="https://example.test/item")


def test_trading_research_scores_above_threshold():
    score, topics = deterministic_classify(candidate("Market microstructure and optimal trade execution", "Order book liquidity and market impact"))
    assert score >= 2
    assert "market_microstructure" in topics


def test_unrelated_machine_learning_is_penalized():
    score, topics = deterministic_classify(candidate("Deep learning for medical image classification"))
    assert score < 2
    assert "machine_learning" in topics


def test_ai_fails_closed_without_free_route(monkeypatch):
    monkeypatch.setenv("TEST_MODEL", "paid-auto")
    config = {
        "enabled": True, "base_url_env": "TEST_URL", "api_key_env": "TEST_KEY",
        "model_env": "TEST_MODEL", "required_model_name_fragment": "free",
        "max_calls_per_run": 1, "max_input_tokens_per_run": 10,
        "max_chars_per_document": 10, "max_output_tokens": 10,
    }
    client = ZeroCostOmniRoute(config)
    result = client.classify(candidate("Trading"), "text")
    assert result.status == "stopped"
    assert client.calls == 0


def test_ai_stops_after_gateway_transport_failure(monkeypatch):
    monkeypatch.setenv("TEST_MODEL", "free-research")
    monkeypatch.setattr(httpx, "post", lambda *_args, **_kwargs: (_ for _ in ()).throw(httpx.ConnectError("offline")))
    config = {
        "enabled": True, "base_url_env": "TEST_URL", "api_key_env": "TEST_KEY",
        "model_env": "TEST_MODEL", "required_model_name_fragment": "free",
        "max_calls_per_run": 2, "max_input_tokens_per_run": 100,
        "max_chars_per_document": 20, "max_output_tokens": 10,
    }
    client = ZeroCostOmniRoute(config)
    first = client.classify(candidate("Trading"), "text")
    second = client.classify(candidate("Trading"), "text")
    assert first.status == "stopped"
    assert second.status == "stopped"
    assert client.calls == 1


def test_ai_requests_non_streaming_json_response(monkeypatch):
    monkeypatch.setenv("TEST_MODEL", "free-research")
    request_body = {}

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [{"message": {"content": '{"accepted":true,"relevance_score":0.9,"topics":["market_microstructure"],"reason":"useful"}'}}]
            }

    def fake_post(*_args, **kwargs):
        request_body.update(kwargs["json"])
        return Response()

    monkeypatch.setattr(httpx, "post", fake_post)
    config = {
        "enabled": True, "base_url_env": "TEST_URL", "api_key_env": "TEST_KEY",
        "model_env": "TEST_MODEL", "required_model_name_fragment": "free",
        "max_calls_per_run": 1, "max_input_tokens_per_run": 100,
        "max_chars_per_document": 20, "max_output_tokens": 100,
    }

    result = ZeroCostOmniRoute(config).classify(candidate("Trade execution"), "order book")

    assert request_body["stream"] is False
    assert result.status == "classified"
