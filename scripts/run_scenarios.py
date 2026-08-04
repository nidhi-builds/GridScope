import argparse
import json
import sys
import time
from urllib.request import Request, urlopen


def request(base_url: str, path: str, method: str = "GET", body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    request = Request(f"{base_url.rstrip('/')}/api/v1/simulator{path}", data=data, method=method, headers={"Content-Type": "application/json"})
    with urlopen(request) as response:  # nosec B310 - reviewer supplied local base URL
        return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--seed", type=int, default=20260803)
    args = parser.parse_args()
    failed = False
    try:
        for definition in request(args.base_url, "/scenarios"):
            request(args.base_url, "/reset", "POST")
            run = request(args.base_url, "/runs", "POST", {"scenario_key": definition["key"], "seed": args.seed})
            while run["status"] == "running":
                time.sleep(0.1)
                run = request(args.base_url, f"/runs/{run['id']}")
            line = {"scenario": definition["key"], "status": run["status"], "observability": definition["observability"], "expected": run["expected"], "actual": run["actual"]}
            print(json.dumps(line, default=str))
            failed |= definition["observability"] == "observable" and run["actual"].get("outcome") != "matched"
    finally:
        request(args.base_url, "/reset", "POST")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
