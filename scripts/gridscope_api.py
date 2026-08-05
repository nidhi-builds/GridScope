"""Minimal stdlib client so the measurement runners use only the public API."""

import json
import os
import time
import urllib.error
import urllib.request


BASE_URL = os.environ.get("GRIDSCOPE_BASE_URL", "http://localhost:8000")


class ApiError(RuntimeError):
    pass


def _call(method: str, path: str, payload: dict | None = None, timeout: float = 300.0) -> dict | list:
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(  # noqa: S310 - fixed local base URL
        f"{BASE_URL}/api/v1{path}", data=data, method=method,
        headers={"Accept": "application/json", **({"Content-Type": "application/json"} if data else {})},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise ApiError(f"{method} {path} -> {error.code}: {error.read()[:400]!r}") from error
    except urllib.error.URLError as error:
        raise ApiError(f"{method} {path} unreachable: {error.reason}") from error


def get(path: str) -> dict | list:
    return _call("GET", path)


def post(path: str, payload: dict | None = None) -> dict | list:
    return _call("POST", path, payload)


def wait_for_ready(attempts: int = 60) -> dict:
    """Block until the stack is genuinely serving, so run 1 is not an outlier."""
    for attempt in range(attempts):
        try:
            return get("/ready")
        except ApiError:
            if attempt == attempts - 1:
                raise
            time.sleep(2)
    raise ApiError("readiness never reported ready")


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round(fraction * len(ordered) + 0.5)) - 1))
    return ordered[index]


def summarize(values: list[float]) -> dict:
    if not values:
        return {"samples": 0}
    return {
        "samples": len(values),
        "min": min(values),
        "p50": percentile(values, 0.50),
        "p95": percentile(values, 0.95),
        "p99": percentile(values, 0.99),
        "max": max(values),
        "mean": sum(values) / len(values),
    }
