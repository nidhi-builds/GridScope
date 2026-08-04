from app.ai.service import create_explanation, request_explanation
from app.config import Settings
from app.db.models.incidents import AIExplanation


def _settings(key: str | None) -> Settings:
    return Settings(_env_file=None, gemini_api_key=key)


def test_missing_key_returns_and_persists_deterministic_bilingual_fallback(session, seeded_incident):
    result = create_explanation(session, seeded_incident, settings=_settings(None))

    saved = session.get(AIExplanation, result.id)
    assert result.fallback_reason == "missing_api_key"
    assert result.validated_text["english"]
    assert result.validated_text["kannada"]
    assert saved.model is None


def test_model_cannot_change_protected_facts(session, seeded_incident):
    facts = __import__("app.ai.summary", fromlist=["facts_from_incident"]).facts_from_incident(session, seeded_incident)

    result = request_explanation(
        facts,
        settings=_settings("test-key"),
        requester=lambda *_: {
            "english": "Wrong result",
            "kannada": "ತಪ್ಪು ಫಲಿತಾಂಶ",
            "protected": {**facts.protected, "affected_count": 999},
        },
    )

    assert result.used_fallback is True
    assert result.fallback_reason == "protected_fact_mismatch"
    assert result.explanation.english != "Wrong result"
    assert result.explanation.kannada


def test_valid_model_response_preserves_facts_and_usage(session, seeded_incident):
    facts = __import__("app.ai.summary", fromlist=["facts_from_incident"]).facts_from_incident(session, seeded_incident)

    result = request_explanation(
        facts,
        settings=_settings("test-key"),
        requester=lambda *_: {
            "english": "A confirmed span fault is being handled.",
            "kannada": "ದೃಢೀಕೃತ ಸ್ಪ್ಯಾನ್ ದೋಷವನ್ನು ನಿರ್ವಹಿಸಲಾಗುತ್ತಿದೆ.",
            "protected": facts.protected,
            "usage": {"input_tokens": 12, "output_tokens": 18},
        },
    )

    assert result.used_fallback is False
    assert result.explanation.english.startswith("A confirmed")
    assert result.explanation.kannada
    assert result.usage == {"input_tokens": 12, "output_tokens": 18}


def test_timeout_and_malformed_responses_fallback_to_bilingual(session, seeded_incident):
    facts = __import__("app.ai.summary", fromlist=["facts_from_incident"]).facts_from_incident(session, seeded_incident)

    timed_out = request_explanation(
        facts, settings=_settings("test-key"), requester=lambda *_: (_ for _ in ()).throw(TimeoutError()),
    )
    malformed = request_explanation(facts, settings=_settings("test-key"), requester=lambda *_: {"english": "missing protected"})

    assert timed_out.fallback_reason == "timeout"
    assert timed_out.explanation.kannada
    assert malformed.fallback_reason == "malformed_response"
    assert malformed.explanation.kannada


def test_api_error_uses_the_bilingual_fallback(session, seeded_incident):
    facts = __import__("app.ai.summary", fromlist=["facts_from_incident"]).facts_from_incident(session, seeded_incident)

    result = request_explanation(
        facts, settings=_settings("test-key"), requester=lambda *_: (_ for _ in ()).throw(RuntimeError("upstream")),
    )

    assert result.fallback_reason == "api_error"
    assert result.explanation.kannada


def test_persists_generated_model_usage_latency_and_fallback_reason(session, seeded_incident):
    facts = __import__("app.ai.summary", fromlist=["facts_from_incident"]).facts_from_incident(session, seeded_incident)
    row = create_explanation(
        session, seeded_incident, settings=_settings("test-key"), requester=lambda *_: {
            "english": "A confirmed span fault is being handled.", "kannada": "ದೃಢೀಕೃತ ಸ್ಪ್ಯಾನ್ ದೋಷವನ್ನು ನಿರ್ವಹಿಸಲಾಗುತ್ತಿದೆ.",
            "protected": facts.protected, "usage": {"input_tokens": 12, "output_tokens": 18},
        },
    )

    saved = session.get(AIExplanation, row.id)
    assert (saved.model, saved.usage, saved.fallback_reason) == ("gemini-2.5-flash", {"input_tokens": 12, "output_tokens": 18}, None)
    assert saved.latency_ms is not None
