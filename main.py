import json
import logging
import os
import secrets
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

app = FastAPI(title="Signal Feed API", version="0.2.0")
logger = logging.getLogger("signal-feed-api")

PUBLISH_API_KEY = os.environ.get("PUBLISH_API_KEY", "")
READ_API_KEYS = {
    key.strip()
    for key in os.environ.get("READ_API_KEYS", "").split(",")
    if key.strip()
}


def load_read_api_acl() -> dict[str, dict[str, Any]]:
    raw_acl = os.environ.get("READ_API_ACL", "").strip()
    if not raw_acl:
        return {}

    try:
        acl = json.loads(raw_acl)
    except json.JSONDecodeError as exc:
        raise RuntimeError("READ_API_ACL must be valid JSON") from exc

    if not isinstance(acl, dict):
        raise RuntimeError("READ_API_ACL must be a JSON object")
    return acl


READ_API_ACL = load_read_api_acl()


class SignalIn(BaseModel):
    model_config = ConfigDict(extra="allow")

    channel: str
    asset: str
    signal: str | None = None
    strategy_id: str | None = None
    strategy_name: str | None = None
    strategy_version: str | None = None
    universe: str | None = None
    as_of_date: date | None = None
    signals: dict[str, Any] = Field(default_factory=dict)
    owner: str | None = None
    value: float | None = None
    confidence: float | None = None
    source: str | None = None
    expires_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SignalOut(SignalIn):
    id: str
    published_at: datetime


latest_signal: SignalOut | None = None
latest_signals: dict[tuple[str, str], SignalOut] = {}


@dataclass(frozen=True)
class ReaderIdentity:
    account: str
    permissions: tuple[str, ...]
    is_legacy: bool = False


def extract_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    scheme, separator, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not separator or not token.strip():
        raise HTTPException(status_code=401, detail="Authorization must use Bearer token")
    return token.strip()


def require_reader(authorization: str | None) -> ReaderIdentity:
    credential = extract_token(authorization)

    account, separator, token = credential.partition(":")
    if separator and account and token:
        reader = READ_API_ACL.get(account)
        if isinstance(reader, dict):
            expected_token = reader.get("token")
            permissions = reader.get("allow")
            if (
                isinstance(expected_token, str)
                and isinstance(permissions, list)
                and all(isinstance(permission, str) for permission in permissions)
                and secrets.compare_digest(token, expected_token)
            ):
                return ReaderIdentity(account=account, permissions=tuple(permissions))

    if any(secrets.compare_digest(credential, key) for key in READ_API_KEYS):
        return ReaderIdentity(
            account="legacy-reader",
            permissions=("*:*",),
            is_legacy=True,
        )

    raise HTTPException(status_code=403, detail="Invalid reader credential")


def can_read(reader: ReaderIdentity, channel: str, asset: str) -> bool:
    allowed_patterns = {
        f"{channel}:{asset}",
        f"{channel}:*",
        f"*:{asset}",
        "*:*",
    }
    return any(permission in allowed_patterns for permission in reader.permissions)


def require_publisher(authorization: str | None) -> None:
    token = extract_token(authorization)
    if not PUBLISH_API_KEY or not secrets.compare_digest(token, PUBLISH_API_KEY):
        raise HTTPException(status_code=403, detail="Invalid publish API key")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "signal-feed-api"}


@app.post("/v1/publish", response_model=SignalOut, response_model_exclude_unset=True, response_model_exclude_none=True)
def publish_signal(
    signal: SignalIn,
    authorization: str | None = Header(default=None),
) -> SignalOut:
    global latest_signal
    require_publisher(authorization)
    latest_signal = SignalOut(
        **signal.model_dump(exclude_unset=True),
        id=secrets.token_urlsafe(12),
        published_at=datetime.now(timezone.utc),
    )
    latest_signals[(signal.channel, signal.asset)] = latest_signal
    return latest_signal


@app.get("/v1/latest", response_model=SignalOut, response_model_exclude_unset=True, response_model_exclude_none=True)
def get_latest_signal(
    channel: str | None = None,
    asset: str | None = None,
    authorization: str | None = Header(default=None),
) -> SignalOut:
    reader = require_reader(authorization)

    if (channel is None) != (asset is None):
        raise HTTPException(
            status_code=400,
            detail="channel and asset must be provided together",
        )

    if channel is not None and asset is not None:
        requested_channel = channel
        requested_asset = asset
        signal = latest_signals.get((channel, asset))
    else:
        signal = latest_signal
        if signal is None:
            raise HTTPException(status_code=404, detail="No signal has been published yet")
        requested_channel = signal.channel
        requested_asset = signal.asset

    if not can_read(reader, requested_channel, requested_asset):
        raise HTTPException(
            status_code=403,
            detail="Reader is not allowed to access this signal",
        )

    if signal is None:
        raise HTTPException(
            status_code=404,
            detail="No signal has been published for this channel and asset",
        )

    logger.info(
        "signal_read account=%s channel=%s asset=%s",
        reader.account,
        requested_channel,
        requested_asset,
    )
    return signal
