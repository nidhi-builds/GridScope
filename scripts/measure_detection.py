"""Measure fault-to-visible and repair-to-verified latency across many runs.

Both timings are wall clock over the public API: from the moment a fault is
injected until the incident is returned by ``GET /incidents``, and from the
moment a repair is requested until the incident reports ``verified`` or
``closed``. The simulator drives its own inbox deterministically, so these are
processing latencies rather than a wall-clock replay of the 15-minute heartbeat
cycle. That distinction is recorded in the output rather than hidden.
"""

import argparse
import json
import sys
import time
from pathlib import Path

from gridscope_api import ApiError, get, post, summarize, wait_for_ready


# Observable scenarios spanning fault class, topology source, noise, and branch size.
OBSERVABLE = (
    "known_span", "inferred_span", "weak_inferred", "missing_endpoints",
    "dt_fault", "feeder_fault", "three_branch_faults", "tier_one",
    "same_path_faults", "real_fault_during_schedule",
)
TARGET_SECONDS = 120.0


def _visible(incident_id: str) -> bool:
    page = get("/incidents?page=1&page_size=100")
    return any(item["id"] == incident_id for item in page["items"])


def _await_visible(incident_id: str, deadline_seconds: float = 180.0) -> float:
    started = time.monotonic()
    while time.monotonic() - started < deadline_seconds:
        if _visible(incident_id):
            return time.monotonic() - started
        time.sleep(0.5)
    raise ApiError(f"incident {incident_id} never became visible")


def _await_closed(incident_id: str, deadline_seconds: float = 180.0) -> tuple[float, str]:
    started = time.monotonic()
    while time.monotonic() - started < deadline_seconds:
        status = get(f"/incidents/{incident_id}")["status"]
        if status in {"verified", "closed"}:
            return time.monotonic() - started, status
        time.sleep(0.5)
    return time.monotonic() - started, get(f"/incidents/{incident_id}")["status"]


def measure(runs: int, seed_base: int) -> dict:
    detection: list[float] = []
    restoration: list[float] = []
    failures: list[dict] = []
    per_scenario: dict[str, list[float]] = {}

    for index in range(runs):
        scenario = OBSERVABLE[index % len(OBSERVABLE)]
        seed = seed_base + index
        try:
            post("/simulator/reset")
            injected_at = time.monotonic()
            run = post("/simulator/runs", {"scenario_key": scenario, "seed": seed})
            incident_ids = run.get("incident_ids") or []
            if not incident_ids:
                failures.append({"run": index, "scenario": scenario, "seed": seed, "reason": "no incident generated"})
                continue

            incident_id = incident_ids[0]
            _await_visible(incident_id)
            detected = time.monotonic() - injected_at
            detection.append(detected)
            per_scenario.setdefault(scenario, []).append(detected)

            repaired_at = time.monotonic()
            post(f"/simulator/runs/{run['id']}/repair")
            _, status = _await_closed(incident_id)
            restored = time.monotonic() - repaired_at
            if status in {"verified", "closed"}:
                restoration.append(restored)
            else:
                failures.append({"run": index, "scenario": scenario, "seed": seed, "reason": f"ended in {status}"})
        except ApiError as error:
            failures.append({"run": index, "scenario": scenario, "seed": seed, "reason": str(error)[:300]})

        print(f"  run {index + 1}/{runs} {scenario}", file=sys.stderr, flush=True)

    detection_summary = summarize(detection)
    restoration_summary = summarize(restoration)
    return {
        "requested_runs": runs,
        "scenarios": list(OBSERVABLE),
        "target_p95_seconds": TARGET_SECONDS,
        "timing_basis": "wall clock over the public API; simulator processes its inbox deterministically",
        "detection_seconds": detection_summary,
        "restoration_seconds": restoration_summary,
        "detection_within_target": bool(detection) and detection_summary["p95"] < TARGET_SECONDS,
        "restoration_within_target": bool(restoration) and restoration_summary["p95"] < TARGET_SECONDS,
        "detection_by_scenario": {name: summarize(values) for name, values in sorted(per_scenario.items())},
        "failure_count": len(failures),
        "failures": failures,
        "detection_samples_seconds": detection,
        "restoration_samples_seconds": restoration,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=100)
    parser.add_argument("--seed-base", type=int, default=20260803)
    parser.add_argument("--output", type=Path, default=Path("performance/results/detection.json"))
    arguments = parser.parse_args()

    wait_for_ready()
    result = measure(arguments.runs, arguments.seed_base)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "detection_p95": result["detection_seconds"].get("p95"),
        "restoration_p95": result["restoration_seconds"].get("p95"),
        "failures": result["failure_count"],
        "output": str(arguments.output),
    }, indent=2))
    # A missed target is reported honestly through the exit code; the raw file stays.
    return 0 if result["detection_within_target"] and result["restoration_within_target"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
