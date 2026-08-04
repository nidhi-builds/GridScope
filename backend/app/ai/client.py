import json
from urllib.error import URLError
from urllib.request import Request, urlopen

from app.ai.schemas import IncidentExplanationFacts
from app.config import Settings


class GeminiRequestError(RuntimeError):
    pass


def request_gemini(facts: IncidentExplanationFacts, settings: Settings) -> dict:
    prompt = {
        "contents": [{"parts": [{"text": (
            "Return JSON only. Write concise operational wording in English and Kannada. "
            "Return exactly {english, kannada, protected}; do not diagnose, add facts, or change protected facts. "
            "Echo protected exactly. "
            f"Facts: {json.dumps({**facts.protected, 'confidence_reasons': facts.confidence_reasons, 'unknowns': facts.unknowns, 'pin_code': facts.pin_code})}"
        )}]}],
        "generationConfig": {
            "temperature": 0.2, "maxOutputTokens": 300, "responseMimeType": "application/json",
            "responseSchema": _response_schema(),
        },
    }
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent"
    request = Request(
        endpoint, data=json.dumps(prompt).encode(), method="POST",
        headers={"Content-Type": "application/json", "x-goog-api-key": settings.gemini_api_key or ""},
    )
    try:
        with urlopen(request, timeout=5) as response:  # nosec B310: fixed HTTPS Gemini endpoint
            payload = json.load(response)
    except TimeoutError as error:
        raise GeminiRequestError("timeout") from error
    except (URLError, OSError) as error:
        raise GeminiRequestError(type(error).__name__) from error
    try:
        text = payload["candidates"][0]["content"]["parts"][0]["text"]
        result = json.loads(text)
        usage = payload.get("usageMetadata", {})
        result["usage"] = {
            "input_tokens": int(usage.get("promptTokenCount", 0)),
            "output_tokens": int(usage.get("candidatesTokenCount", 0)),
        }
        return result
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise GeminiRequestError("malformed_response") from error


def _response_schema() -> dict:
    protected = {
        "incident_id": {"type": "STRING"}, "fault_class": {"type": "STRING"},
        "location_class": {"type": "STRING"}, "affected_count": {"type": "INTEGER"},
        "confidence": {"type": "STRING"}, "status": {"type": "STRING"},
        "asset_ids": {"type": "ARRAY", "items": {"type": "STRING"}},
        "boundary_ids": {"type": "ARRAY", "items": {"type": "STRING"}},
        "navigation": {"type": "ARRAY", "items": {"type": "NUMBER"}},
    }
    return {
        "type": "OBJECT", "properties": {
            "english": {"type": "STRING"}, "kannada": {"type": "STRING"},
            "protected": {"type": "OBJECT", "properties": protected, "required": list(protected), "additionalProperties": False},
        }, "required": ["english", "kannada", "protected"], "additionalProperties": False,
    }
