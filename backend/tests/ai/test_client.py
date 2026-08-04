import io
import json

from app.ai.client import request_gemini
from app.ai.schemas import IncidentExplanationFacts
from app.config import Settings


FACTS = IncidentExplanationFacts(
    incident_id="incident-1", fault_class="span", location_class="span", affected_count=2,
    confidence="high", status="detected", asset_ids=("pole-1",), boundary_ids=("pole-1",),
    confidence_reasons=("direct dark",), unknowns=(), navigation=(12.0, 77.0), pin_code="1234",
)


def test_gemini_request_sets_five_second_timeout_and_explicit_response_schema(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return _Response({"candidates": [{"content": {"parts": [{"text": json.dumps({
            "english": "English", "kannada": "ಕನ್ನಡ", "protected": FACTS.protected,
        })}]}}]})

    monkeypatch.setattr("app.ai.client.urlopen", fake_urlopen)

    result = request_gemini(FACTS, Settings(_env_file=None, gemini_api_key="test-key"))
    request = json.loads(captured["request"].data)

    assert captured["timeout"] == 5
    assert request["generationConfig"]["responseMimeType"] == "application/json"
    assert set(request["generationConfig"]["responseSchema"]["properties"]) == {"english", "kannada", "protected"}
    assert request["generationConfig"]["responseSchema"]["properties"]["protected"]["required"] == list(FACTS.protected)
    assert result["protected"] == FACTS.protected


class _Response(io.StringIO):
    def __init__(self, payload):
        super().__init__(json.dumps(payload))

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
