"""Scripted demo: inject a fault, show the localized ticket, prove the map data.

Everything here goes through the public API a device would use. Run it beside a
screen recording; each step prints a heading, so the narration has something to
point at.

    python scripts/demo_ingest.py                       # against localhost
    python scripts/demo_ingest.py --base-url https://<your-app>.onrender.com
"""

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gridscope_api import ApiError, get, post, wait_for_ready  # noqa: E402


def _heading(step: str, title: str) -> None:
    print(f"\n{'=' * 68}\n  {step}  {title}\n{'=' * 68}")


def _raw_ingest_demo() -> None:
    """Duplicate rejection, on any real device, through the public contract."""
    _heading("1", "Raw telemetry ingest: the same message twice")
    device = get("/device-health?page=1&page_size=1")["items"][0]
    payload = {
        "device_id": device["device_id"],
        "pole_id": device["pole_id"],
        "seq": int(time.time()),
        "ts": datetime.now(UTC).isoformat(),
        "event_type": "heartbeat",
        "energized": True,
        "battery": 82,
        "rssi": -91,
    }
    first = post("/telemetry", payload)
    second = post("/telemetry", payload)
    print(f"  device        {device['serial_number']} on pole {device['pole_id'][:8]}")
    print(f"  first send    -> {first['outcome']}   (stored, event {str(first['event_id'])[:8]})")
    print(f"  identical re-send -> {second['outcome']}   (rejected by fingerprint, not stored twice)")


def _inject(scenario: str) -> dict:
    post("/simulator/reset")
    return post("/simulator/runs", {"scenario_key": scenario, "seed": 20260803})


def _show_incident(incident_id: str) -> dict:
    detail = get(f"/incidents/{incident_id}")
    boundary = detail["boundary"]
    print(f"  incident       {incident_id[:8]}   status {detail['status']}")
    print(f"  what failed    {detail['fault_class']} / boundary kind: {boundary['kind']}")
    print(f"  where          {detail['navigation']['latitude']:.5f}, {detail['navigation']['longitude']:.5f}")
    print(f"  PIN            {detail['pin']['value'] or 'unavailable'} (source: {detail['pin']['source']})")
    print(f"  affected       {detail['affected_count']} poles"
          f"{' (estimated - topology inferred)' if detail['affected_count_estimated'] else ''}")
    print(f"  confidence     {detail['confidence']['level']}")
    for reason in detail["confidence"]["reasons"][:5]:
        print(f"                 - {reason}")
    print(f"  topology       {detail['topology']['source']}")
    counts = ", ".join(f"{count} {name.replace('_', ' ')}" for name, count in detail["evidence"]["class_counts"].items())
    print(f"  evidence       {counts or 'none'}")
    return detail


def _show_map(incident_id: str) -> None:
    geometry = get(f"/network/incidents/{incident_id}")
    features = geometry.get("features", [])
    kinds = {feature.get("geometry", {}).get("type") for feature in features}
    print(f"  GeoJSON        {len(features)} feature(s), types: {', '.join(sorted(k for k in kinds if k)) or 'none'}")
    scoped = all((feature.get("properties") or {}).get("incident_id") == incident_id for feature in features)
    print(f"  scoped         {'yes - only this incident renders' if scoped else 'NO - stale geometry present'}")
    if not features:
        print("  NOTE           no geometry: the map will centre on the incident but draw no line")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--skip-raw", action="store_true", help="skip the duplicate-ingest step")
    arguments = parser.parse_args()
    if arguments.base_url:
        os.environ["GRIDSCOPE_BASE_URL"] = arguments.base_url

    try:
        readiness = wait_for_ready()
    except ApiError as error:
        print(f"API not reachable: {error}")
        return 1
    print(f"ready: database={readiness['database']} seed={readiness['seed']} "
          f"worker={readiness['worker']} ai={readiness.get('ai')}")

    if not arguments.skip_raw:
        _raw_ingest_demo()

    _heading("2", "Inject a known-topology span fault")
    run = _inject("known_span")
    print(f"  run            {run['id'][:8]}   scenario {run['scenario']}")
    print(f"  expected       {run['expected']['incident_count']} {'/'.join(run['expected']['classes'])} incident")
    print(f"  actual         {run['actual']['incident_count']} "
          f"{'/'.join(run['actual']['classes'])} incident   -> {run['actual']['outcome']}")
    print(f"  hidden truth   {len(run['truth'].get('deenergized', []))} poles de-energized "
          f"(demo view only)")
    if not run["incident_ids"]:
        print("  no incident generated; try a different seed")
        return 1

    incident_id = run["incident_ids"][0]
    _heading("3", "The ticket an operator sees")
    _show_incident(incident_id)

    _heading("4", "Map data for this incident")
    _show_map(incident_id)

    _heading("5", "Reporting a repair while poles are still dark")
    try:
        post(f"/incidents/{incident_id}/acknowledge", {"actor": "demo"})
        post(f"/incidents/{incident_id}/assign", {"actor": "demo", "crew_label": "crew-1"})
        post(f"/incidents/{incident_id}/report-resolved", {"actor": "demo"})
        print("  UNEXPECTED     the premature repair was accepted")
    except ApiError as error:
        print(f"  rejected       {str(error)[:140]}")
        print("  meaning        closure needs restoration telemetry, not a button click")

    _heading("6", "Real repair, then telemetry-verified closure")
    post(f"/simulator/runs/{run['id']}/repair")
    for _ in range(30):
        status = get(f"/incidents/{incident_id}")["status"]
        if status in {"verified", "closed"}:
            break
        time.sleep(1)
    final = get(f"/incidents/{incident_id}")
    print(f"  final status   {final['status']}")
    print("  ticket history")
    for event in final["ticket_events"]:
        print(f"                 {event['type']:<16} {event['reason'][:60]}")

    _heading("7", "Noise that must not raise a ticket")
    for scenario in ("device_death", "reboot_replay"):
        quiet = _inject(scenario)
        print(f"  {scenario:<15} tickets opened: {len(quiet['incident_ids'])}")

    _heading("8", "Three simultaneous faults stay three tickets")
    three = _inject("three_branch_faults")
    print(f"  expected {three['expected']['incident_count']}, got {len(three['incident_ids'])}")

    print("\nDone. Reset with: curl -X POST $BASE/api/v1/simulator/reset\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
