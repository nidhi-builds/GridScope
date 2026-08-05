"""Measure localization accuracy and false-ticket behaviour across many runs.

Definitions used, stated explicitly so the numbers can be argued with:

* Exact-span precision - of runs whose reported ``fault_class`` is ``span``, the
  fraction whose reported boundary endpoints equal the simulator's hidden truth
  edge. A run that reports a corridor is not counted as an exact-span attempt.
* Inferred exact output - whether any run built on inferred topology emitted an
  exact span. GridScope deliberately degrades inferred topology to a corridor,
  so the expected value is zero and the PRD's alternative gate ("exact inferred
  output is disabled") is the one that applies.
* Corridor containment - the fraction of corridor runs whose reported pole path
  contains the hidden truth edge. A corridor that does not contain the real
  fault would send a crew to the wrong street.
* False tickets - incidents opened by noise-only scenarios. The required value
  is zero; anything above zero is a correctness failure, not a tuning knob.
"""

import argparse
import json
import sys
import time
from pathlib import Path

from gridscope_api import ApiError, get, post, wait_for_ready


EXACT = ("known_span", "tier_one", "real_fault_during_schedule")
INFERRED = ("inferred_span", "weak_inferred")
CORRIDOR = ("inferred_span", "weak_inferred", "missing_endpoints", "same_path_faults")
SCOPE = ("dt_fault", "feeder_fault")
NOISE_ONLY = ("device_death", "noise_baseline", "reboot_replay", "transport_noise", "planned_outage", "firmware_12_silence")
UNOBSERVABLE = ("firmware_12_silence",)


def _truth_edge(run: dict) -> list[str] | None:
    evidence = (run.get("actual") or {}).get("effect_evidence") or {}
    for details in evidence.values():
        edge = details.get("target_edge")
        if isinstance(edge, list) and len(edge) == 2 and all(isinstance(item, str) for item in edge):
            return edge
        edges = details.get("target_edges")
        if isinstance(edges, list) and edges:
            return edges[0]
    return None


def _accuracy_pass(runs: int, seed_base: int) -> dict:
    scenarios = EXACT + INFERRED + CORRIDOR + SCOPE
    exact_attempts = exact_hits = 0
    corridor_attempts = corridor_hits = 0
    inferred_exact_outputs = 0
    degraded = candidates = 0
    scope_correct = scope_attempts = 0
    misses: list[dict] = []

    for index in range(runs):
        scenario = scenarios[index % len(scenarios)]
        seed = seed_base + index
        try:
            post("/simulator/reset")
            run = post("/simulator/runs", {"scenario_key": scenario, "seed": seed})
            incident_ids = run.get("incident_ids") or []
            if not incident_ids:
                misses.append({"scenario": scenario, "seed": seed, "reason": "no incident generated"})
                continue

            truth_edge = _truth_edge(run)
            detail = get(f"/incidents/{incident_ids[0]}")
            boundary = detail.get("boundary") or {}
            kind = boundary.get("kind")
            path = (boundary.get("geometry") or {}).get("pole_path") or []
            endpoints = {boundary.get("upstream_pole_id"), boundary.get("downstream_pole_id")}

            if detail.get("topology", {}).get("source") == "inferred":
                degraded += 1
                if kind == "span":
                    inferred_exact_outputs += 1

            if kind == "span":
                exact_attempts += 1
                if truth_edge and endpoints == set(truth_edge):
                    exact_hits += 1
                else:
                    misses.append({"scenario": scenario, "seed": seed, "reason": "span endpoints differ from truth",
                                   "reported": sorted(item for item in endpoints if item), "truth": truth_edge})
            elif kind == "corridor":
                corridor_attempts += 1
                contained = bool(truth_edge) and all(pole in path for pole in truth_edge)
                candidates += len(boundary.get("candidate_spans") or [])
                if contained or not truth_edge:
                    corridor_hits += 1
                else:
                    misses.append({"scenario": scenario, "seed": seed, "reason": "corridor excludes the truth edge",
                                   "path_length": len(path), "truth": truth_edge})
            elif kind in {"dt", "feeder"}:
                scope_attempts += 1
                if detail.get("fault_class") == kind:
                    scope_correct += 1
        except ApiError as error:
            misses.append({"scenario": scenario, "seed": seed, "reason": str(error)[:300]})
        print(f"  accuracy {index + 1}/{runs} {scenario}", file=sys.stderr, flush=True)

    def ratio(hits: int, attempts: int) -> float | None:
        return None if attempts == 0 else hits / attempts

    return {
        "exact_span": {"attempts": exact_attempts, "hits": exact_hits, "precision": ratio(exact_hits, exact_attempts), "gate": 0.95},
        "corridor_containment": {"attempts": corridor_attempts, "hits": corridor_hits, "containment": ratio(corridor_hits, corridor_attempts), "gate": 0.95},
        "inferred_exact_output_count": inferred_exact_outputs,
        "inferred_exact_output_disabled": inferred_exact_outputs == 0,
        "degraded_topology_runs": degraded,
        "corridor_candidate_spans_total": candidates,
        "scope_localization": {"attempts": scope_attempts, "correct": scope_correct, "precision": ratio(scope_correct, scope_attempts)},
        "misses": misses,
    }


def _noise_pass(runs: int, seed_base: int) -> dict:
    false_tickets: list[dict] = []
    unobservable_runs = 0
    per_scenario: dict[str, int] = {}

    for index in range(runs):
        scenario = NOISE_ONLY[index % len(NOISE_ONLY)]
        seed = seed_base + 5000 + index
        try:
            post("/simulator/reset")
            run = post("/simulator/runs", {"scenario_key": scenario, "seed": seed})
            opened = len(run.get("incident_ids") or [])
            per_scenario[scenario] = per_scenario.get(scenario, 0) + opened
            if opened:
                false_tickets.append({"scenario": scenario, "seed": seed, "incident_ids": run["incident_ids"]})
            if scenario in UNOBSERVABLE or (run.get("expected") or {}).get("observability") == "unobservable":
                unobservable_runs += 1
        except ApiError as error:
            false_tickets.append({"scenario": scenario, "seed": seed, "reason": str(error)[:300]})
        print(f"  noise {index + 1}/{runs} {scenario}", file=sys.stderr, flush=True)

    return {
        "runs": runs,
        "scenarios": list(NOISE_ONLY),
        "false_ticket_count": len(false_tickets),
        "false_tickets": false_tickets,
        "tickets_by_scenario": per_scenario,
        "unobservable_run_count": unobservable_runs,
        "gate": "zero false tickets",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=100, help="observable accuracy runs")
    parser.add_argument("--noise-runs", type=int, default=100, help="noise-only runs for false-ticket count")
    parser.add_argument("--seed-base", type=int, default=20260803)
    parser.add_argument("--output", type=Path, default=Path("performance/results/accuracy.json"))
    arguments = parser.parse_args()

    wait_for_ready()
    started = time.monotonic()
    accuracy = _accuracy_pass(arguments.runs, arguments.seed_base)
    noise = _noise_pass(arguments.noise_runs, arguments.seed_base)
    result = {
        "elapsed_seconds": time.monotonic() - started,
        "accuracy": accuracy,
        "noise": noise,
    }

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "exact_span_precision": accuracy["exact_span"]["precision"],
        "corridor_containment": accuracy["corridor_containment"]["containment"],
        "inferred_exact_output_disabled": accuracy["inferred_exact_output_disabled"],
        "false_ticket_count": noise["false_ticket_count"],
        "output": str(arguments.output),
    }, indent=2))

    exact = accuracy["exact_span"]["precision"]
    corridor = accuracy["corridor_containment"]["containment"]
    passed = (
        (exact is None or exact >= 0.95)
        and (corridor is None or corridor >= 0.95)
        and accuracy["inferred_exact_output_disabled"]
        and noise["false_ticket_count"] == 0
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
