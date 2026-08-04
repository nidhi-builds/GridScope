from threading import Thread
from time import monotonic
from typing import Callable
from uuid import UUID

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.ai.client import GeminiRequestError, request_gemini
from app.ai.schemas import Explanation, ExplanationResult, IncidentExplanationFacts, ModelExplanation
from app.ai.summary import facts_from_incident, render_fallback
from app.config import Settings, get_settings
from app.db import SessionLocal
from app.db.models.incidents import AIExplanation, Incident


PROMPT_VERSION = "gemini-v1"
Requester = Callable[[IncidentExplanationFacts, Settings], dict]


def request_explanation(
    facts: IncidentExplanationFacts, settings: Settings | None = None, requester: Requester = request_gemini,
) -> ExplanationResult:
    settings = settings or get_settings()
    started = monotonic()
    if not settings.gemini_api_key:
        return _fallback(facts, "missing_api_key", started)
    try:
        response = ModelExplanation.model_validate(requester(facts, settings))
        if response.protected != facts.protected:
            return _fallback(facts, "protected_fact_mismatch", started)
        return ExplanationResult(
            Explanation(response.english, response.kannada), False, settings.gemini_model, response.usage,
            _latency(started),
        )
    except TimeoutError:
        return _fallback(facts, "timeout", started)
    except GeminiRequestError as error:
        return _fallback(facts, str(error), started)
    except (ValueError, TypeError):
        return _fallback(facts, "malformed_response", started)
    except Exception:
        return _fallback(facts, "api_error", started)


def create_explanation(
    session: Session, incident: Incident, settings: Settings | None = None, requester: Requester = request_gemini,
) -> AIExplanation:
    return _persist_explanation(session, facts_from_incident(session, incident), settings, requester)


def _persist_explanation(
    session: Session, facts: IncidentExplanationFacts, settings: Settings | None = None, requester: Requester = request_gemini,
) -> AIExplanation:
    result = request_explanation(facts, settings, requester)
    row = AIExplanation(
        incident_id=UUID(facts.incident_id), prompt_version=PROMPT_VERSION, model=result.model,
        validated_text=result.explanation.as_dict(), usage=result.usage, latency_ms=result.latency_ms,
        fallback_reason=result.fallback_reason,
    )
    session.add(row)
    session.flush()
    return row


def queue_explanation(session: Session, incident: Incident) -> None:
    session.flush()
    session.info.setdefault("ai_explanation_facts", {})[incident.id] = facts_from_incident(session, incident)


@event.listens_for(Session, "after_commit")
def _start_queued_explanations(session: Session) -> None:
    for facts in session.info.pop("ai_explanation_facts", {}).values():
        Thread(target=_create_after_commit, args=(facts,), daemon=True).start()


@event.listens_for(Session, "after_rollback")
def _discard_queued_explanations(session: Session) -> None:
    session.info.pop("ai_explanation_facts", None)


def _create_after_commit(facts: IncidentExplanationFacts) -> None:
    with SessionLocal.begin() as session:
        if session.get(Incident, UUID(facts.incident_id)):
            _persist_explanation(session, facts)


def _fallback(facts: IncidentExplanationFacts, reason: str, started: float) -> ExplanationResult:
    return ExplanationResult(render_fallback(facts), True, None, {}, _latency(started), reason)


def _latency(started: float) -> int:
    return max(0, round((monotonic() - started) * 1000))
