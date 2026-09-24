#!/usr/bin/env python3
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


DEFAULT_BASE_URL = "https://api-sender-v68f.onrender.com"


def output(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read one Signal Feed identified by channel and asset."
    )
    parser.add_argument(
        "channel",
        nargs="?",
        default=os.environ.get("SIGNAL_DEFAULT_CHANNEL"),
    )
    parser.add_argument(
        "asset",
        nargs="?",
        default=os.environ.get("SIGNAL_DEFAULT_ASSET"),
    )
    parser.add_argument(
        "--date",
        dest="as_of_date",
        help="Read an exact as_of_date in YYYY-MM-DD format; omit for latest.",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("SIGNAL_API_BASE_URL", DEFAULT_BASE_URL),
    )
    args = parser.parse_args()

    if not args.channel or not args.asset:
        output({
            "error": "channel and asset are required",
            "hint": "Pass both arguments or set SIGNAL_DEFAULT_CHANNEL and SIGNAL_DEFAULT_ASSET.",
        })
        return 2

    account = os.environ.get("SIGNAL_API_USER", "").strip()
    token = os.environ.get("SIGNAL_API_TOKEN", "").strip()
    if not account or not token:
        output({
            "error": "SIGNAL_API_USER and SIGNAL_API_TOKEN must be configured",
        })
        return 2

    query_params = {
        "channel": args.channel,
        "asset": args.asset,
    }
    if args.as_of_date:
        query_params["as_of_date"] = args.as_of_date
    query = urllib.parse.urlencode(query_params)
    url = f"{args.base_url.rstrip('/')}/v1/latest?{query}"
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {account}:{token}"},
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = json.loads(response.read().decode("utf-8"))
            output(payload)
            return 0
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("detail")
        except (json.JSONDecodeError, UnicodeDecodeError):
            detail = None

        if exc.code == 404:
            output({
                "status": "no_signal",
                "channel": args.channel,
                "asset": args.asset,
                "detail": detail,
            })
            return 0

        output({
            "error": "signal request failed",
            "status": exc.code,
            "detail": detail,
        })
        return 1
    except (urllib.error.URLError, TimeoutError) as exc:
        output({
            "error": "signal service is unavailable",
            "detail": str(exc.reason) if isinstance(exc, urllib.error.URLError) else "timeout",
        })
        return 1


if __name__ == "__main__":
    sys.exit(main())
