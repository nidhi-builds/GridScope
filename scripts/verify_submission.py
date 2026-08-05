"""Pass/fail gate for the GridScope submission.

Checks only things that can be verified from the repository and, when the stack
is running, from the live API. Every check prints its own verdict so a failure
names the specific missing artefact instead of a single unhelpful exit code.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
REQUIRED_DOCS = ("README.md", "ARCHITECTURE.md", "DEPLOYMENT.md", "DECISIONS.md", "AI-WORKFLOW.md")
RESULT_FILES = ("detection.json", "accuracy.json", "sustained.json", "burst.json", "ui-load.json", "lifecycle.json")
PLACEHOLDER = re.compile(r"(TODO|TBD|FIXME|<[A-Z_ ]{3,}>|https?://(example\.com|your-|placeholder))", re.IGNORECASE)
SECRET = re.compile(r"(AIza[0-9A-Za-z_\-]{20,}|gh[ps]_[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)")
REQUIRED_ROUTES = (
    "/api/v1/health", "/api/v1/ready", "/api/v1/telemetry", "/api/v1/telemetry/batch",
    "/api/v1/incidents", "/api/v1/incidents/{incident_id}", "/api/v1/planned-operations",
    "/api/v1/device-health", "/api/v1/simulator/scenarios", "/api/v1/simulator/runs",
)
EXPECTED_SCENARIO_COUNT = 17


class Report:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.warnings: list[str] = []

    def check(self, label: str, ok: bool, detail: str = "") -> None:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}{f' - {detail}' if detail else ''}")
        if not ok:
            self.failures.append(f"{label}{f': {detail}' if detail else ''}")

    def warn(self, label: str, detail: str) -> None:
        print(f"  [WARN] {label} - {detail}")
        self.warnings.append(f"{label}: {detail}")


def check_documents(report: Report) -> None:
    print("Required root documents")
    for name in REQUIRED_DOCS:
        path = ROOT / name
        report.check(name, path.is_file() and path.stat().st_size > 500,
                     "missing or too short to be real" if not (path.is_file() and path.stat().st_size > 500) else "")


def check_placeholders(report: Report) -> None:
    print("Unresolved markers in shipped documents")
    for name in REQUIRED_DOCS:
        path = ROOT / name
        if not path.is_file():
            continue
        hits = sorted({match.group(0) for match in PLACEHOLDER.finditer(path.read_text(encoding="utf-8", errors="replace"))})
        report.check(f"{name} has no placeholders", not hits, ", ".join(hits[:5]))


def check_tracked_secrets(report: Report) -> None:
    print("Tracked secrets")
    try:
        tracked = subprocess.run(  # noqa: S603
            ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.split()
    except (OSError, subprocess.CalledProcessError) as error:
        report.warn("git ls-files", f"could not read the index ({error})")
        return

    report.check("no tracked .env", ".env" not in tracked)
    offenders = []
    for name in tracked:
        path = ROOT / name
        if not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        try:
            if SECRET.search(path.read_text(encoding="utf-8", errors="ignore")):
                offenders.append(name)
        except OSError:
            continue
    report.check("no API keys or private keys committed", not offenders, ", ".join(offenders[:5]))


def check_openapi(report: Report) -> None:
    print("OpenAPI coverage")
    path = ROOT / "openapi.json"
    if not path.is_file():
        report.check("openapi.json present", False, "run scripts/export_openapi.py")
        return
    paths = json.loads(path.read_text(encoding="utf-8")).get("paths", {})
    missing = [route for route in REQUIRED_ROUTES if route not in paths]
    report.check("every operational route documented", not missing, ", ".join(missing))


def check_results(report: Report, require_results: bool) -> None:
    print("Measured performance evidence")
    directory = ROOT / "performance" / "results"
    for name in RESULT_FILES:
        path = directory / name
        present = path.is_file() and path.stat().st_size > 2
        if present or require_results:
            report.check(f"performance/results/{name}", present, "not produced yet" if not present else "")
        else:
            report.warn(f"performance/results/{name}", "not produced yet; run the suite before submitting")


def check_scenarios(report: Report, base_url: str | None) -> None:
    print("Deterministic scenarios")
    if not base_url:
        report.warn("simulator scenarios", "skipped; pass --base-url to check the live API")
        return
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from gridscope_api import ApiError, get  # noqa: PLC0415

    try:
        scenarios = get("/simulator/scenarios")
    except ApiError as error:
        report.check("simulator scenarios reachable", False, str(error)[:200])
        return
    report.check("all scenario presets exposed", len(scenarios) == EXPECTED_SCENARIO_COUNT,
                 f"found {len(scenarios)}, expected {EXPECTED_SCENARIO_COUNT}")
    unobservable = [item for item in scenarios if item["observability"] != "observable"]
    report.check("unobservable scenarios declared", bool(unobservable),
                 "no scenario declares limited or unobservable observability")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=None, help="check the live API too, e.g. http://localhost:8000")
    parser.add_argument("--require-results", action="store_true",
                        help="treat missing performance results as failures rather than warnings")
    arguments = parser.parse_args()

    if arguments.base_url:
        import os  # noqa: PLC0415
        os.environ["GRIDSCOPE_BASE_URL"] = arguments.base_url

    report = Report()
    check_documents(report)
    check_placeholders(report)
    check_tracked_secrets(report)
    check_openapi(report)
    check_results(report, arguments.require_results)
    check_scenarios(report, arguments.base_url)

    print()
    if report.warnings:
        print(f"{len(report.warnings)} warning(s):")
        for warning in report.warnings:
            print(f"  - {warning}")
    if report.failures:
        print(f"\nSUBMISSION NOT READY - {len(report.failures)} failing check(s):")
        for failure in report.failures:
            print(f"  - {failure}")
        return 1
    print("SUBMISSION CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
