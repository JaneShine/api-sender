#!/usr/bin/env python3
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


BASE_URL = os.environ.get(
    "SIGNAL_API_BASE_URL",
    "https://api-sender-v68f.onrender.com",
).rstrip("/")

PAYLOAD = {
    "channel": "industry",
    "asset": "electronics",
    "strategy_id": "industry_electronics",
    "strategy_name": "量化行业策略：电子（申信）",
    "strategy_version": "1.0",
    "universe": "elec",
    "as_of_date": "2026-09-23",
    "signals": {
        "macro_bull": False,
        "prosperity_bull": True,
        "trading_bull": True,
    },
    "owner": "jxxie@efund",
}


def request_json(method: str, url: str, bearer: str, payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {bearer}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def main() -> int:
    publish_key = os.environ.get("PUBLISH_API_KEY", "").strip()
    account = os.environ.get("SIGNAL_API_USER", "").strip()
    read_token = os.environ.get("SIGNAL_API_TOKEN", "").strip()

    if not publish_key or not account or not read_token:
        print(
            "Missing PUBLISH_API_KEY, SIGNAL_API_USER, or SIGNAL_API_TOKEN",
            file=sys.stderr,
        )
        return 2

    try:
        publish_status, published = request_json(
            "POST",
            f"{BASE_URL}/v1/publish",
            publish_key,
            PAYLOAD,
        )

        query = urllib.parse.urlencode({
            "channel": PAYLOAD["channel"],
            "asset": PAYLOAD["asset"],
        })
        read_status, received = request_json(
            "GET",
            f"{BASE_URL}/v1/latest?{query}",
            f"{account}:{read_token}",
        )
    except urllib.error.HTTPError as exc:
        safe_body = exc.read().decode("utf-8", errors="replace")
        print(f"API request failed: HTTP {exc.code} {safe_body}", file=sys.stderr)
        return 1
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"API request failed: {exc}", file=sys.stderr)
        return 1

    mismatches = {
        key: {"expected": value, "actual": received.get(key)}
        for key, value in PAYLOAD.items()
        if received.get(key) != value
    }
    if mismatches:
        print(json.dumps({"mismatches": mismatches}, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps({
        "ok": True,
        "publish_status": publish_status,
        "read_status": read_status,
        "channel": received["channel"],
        "asset": received["asset"],
        "strategy_id": received["strategy_id"],
        "signals": received["signals"],
        "id": received["id"],
        "published_at": received["published_at"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())