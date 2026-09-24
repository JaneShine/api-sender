import json
import logging
import os
import secrets
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

import psycopg
from fastapi import FastAPI, Header, HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger("signal-feed-api")

PUBLISH_API_KEY = os.environ.get("PUBLISH_API_KEY", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
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
    as_of_date: date
    owner: str = Field(min_length=1)
    signal: str | None = None
    strategy_id: str | None = None
    strategy_name: str | None = None
    strategy_version: str | None = None
    universe: str | None = None
    signals: dict[str, Any] = Field(default_factory=dict)
    value: float | None = None
    confidence: float | None = None
    source: str | None = None
    expires_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SignalOut(SignalIn):
    id: str
    published_at: datetime


latest_signal: SignalOut | None = None
latest_signals: dict[tuple[str, str, date], SignalOut] = {}


@dataclass(frozen=True)
class ReaderIdentity:
    account: str
    permissions: tuple[str, ...]
    is_legacy: bool = False


def initialize_storage() -> None:
    if not DATABASE_URL:
        logger.warning("DATABASE_URL is not configured; using volatile memory storage")
        return

    with psycopg.connect(DATABASE_URL, connect_timeout=10) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS latest_signals (
                channel TEXT NOT NULL,
                asset TEXT NOT NULL,
                payload JSONB NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL,
                PRIMARY KEY (channel, asset)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS signal_snapshots (
                channel TEXT NOT NULL,
                asset TEXT NOT NULL,
                as_of_date DATE NOT NULL,
                payload JSONB NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL,
                PRIMARY KEY (channel, asset, as_of_date)
            )
            """
        )
        connection.execute(
            """
            INSERT INTO signal_snapshots (
                channel,
                asset,
                as_of_date,
                payload,
                updated_at
            )
            SELECT
                channel,
                asset,
                COALESCE(
                    NULLIF(payload->>'as_of_date', '')::date,
                    updated_at::date
                ),
                payload,
                updated_at
            FROM latest_signals
            ON CONFLICT (channel, asset, as_of_date)
            DO UPDATE SET
                payload = EXCLUDED.payload,
                updated_at = EXCLUDED.updated_at
            WHERE EXCLUDED.updated_at > signal_snapshots.updated_at
            """
        )
    logger.info("PostgreSQL signal snapshot storage initialized")


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_storage()
    yield


app = FastAPI(
    title="Signal Feed API",
    version="0.4.0",
    lifespan=lifespan,
)


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
    if separator and account and token and account in READ_API_ACL:
        reader = READ_API_ACL[account]
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

        raise HTTPException(status_code=403, detail="Invalid reader credential")

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


def save_signal(signal: SignalOut) -> None:
    global latest_signal

    if DATABASE_URL:
        payload = signal.model_dump(mode="json", exclude_unset=True)
        try:
            with psycopg.connect(DATABASE_URL, connect_timeout=10) as connection:
                connection.execute(
                    """
                    INSERT INTO signal_snapshots (
                        channel,
                        asset,
                        as_of_date,
                        payload,
                        updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (channel, asset, as_of_date)
                    DO UPDATE SET
                        payload = EXCLUDED.payload,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (
                        signal.channel,
                        signal.asset,
                        signal.as_of_date,
                        Jsonb(payload),
                        signal.published_at,
                    ),
                )
        except psycopg.Error as exc:
            logger.exception("Failed to save signal to PostgreSQL")
            raise HTTPException(
                status_code=503,
                detail="Signal storage is temporarily unavailable",
            ) from exc

    latest_signal = signal
    latest_signals[(signal.channel, signal.asset, signal.as_of_date)] = signal


def load_signal(
    channel: str | None,
    asset: str | None,
    snapshot_date: date | None,
) -> SignalOut | None:
    if DATABASE_URL:
        try:
            with psycopg.connect(DATABASE_URL, connect_timeout=10) as connection:
                if (
                    channel is not None
                    and asset is not None
                    and snapshot_date is not None
                ):
                    row = connection.execute(
                        """
                        SELECT payload
                        FROM signal_snapshots
                        WHERE channel = %s
                          AND asset = %s
                          AND as_of_date = %s
                        """,
                        (channel, asset, snapshot_date),
                    ).fetchone()
                elif channel is not None and asset is not None:
                    row = connection.execute(
                        """
                        SELECT payload
                        FROM signal_snapshots
                        WHERE channel = %s AND asset = %s
                        ORDER BY as_of_date DESC, updated_at DESC
                        LIMIT 1
                        """,
                        (channel, asset),
                    ).fetchone()
                else:
                    row = connection.execute(
                        """
                        SELECT payload
                        FROM signal_snapshots
                        ORDER BY updated_at DESC
                        LIMIT 1
                        """
                    ).fetchone()
        except psycopg.Error as exc:
            logger.exception("Failed to load signal from PostgreSQL")
            raise HTTPException(
                status_code=503,
                detail="Signal storage is temporarily unavailable",
            ) from exc

        return SignalOut.model_validate(row[0]) if row else None

    if channel is not None and asset is not None and snapshot_date is not None:
        return latest_signals.get((channel, asset, snapshot_date))

    if channel is not None and asset is not None:
        matches = [
            signal
            for (stored_channel, stored_asset, _), signal in latest_signals.items()
            if stored_channel == channel and stored_asset == asset
        ]
        return max(matches, key=lambda signal: signal.as_of_date) if matches else None

    return latest_signal


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "signal-feed-api",
        "storage": "postgresql" if DATABASE_URL else "memory",
    }


@app.post(
    "/v1/publish",
    response_model=SignalOut,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
def publish_signal(
    signal: SignalIn,
    authorization: str | None = Header(default=None),
) -> SignalOut:
    require_publisher(authorization)
    published_signal = SignalOut(
        **signal.model_dump(exclude_unset=True),
        id=secrets.token_urlsafe(12),
        published_at=datetime.now(timezone.utc),
    )
    save_signal(published_signal)
    return published_signal


@app.get(
    "/v1/latest",
    response_model=SignalOut,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
def get_latest_signal(
    channel: str | None = None,
    asset: str | None = None,
    as_of_date: date | None = None,
    authorization: str | None = Header(default=None),
) -> SignalOut:
    reader = require_reader(authorization)

    if (channel is None) != (asset is None):
        raise HTTPException(
            status_code=400,
            detail="channel and asset must be provided together",
        )
    if as_of_date is not None and (channel is None or asset is None):
        raise HTTPException(
            status_code=400,
            detail="as_of_date requires channel and asset",
        )

    signal = load_signal(channel, asset, as_of_date)
    if signal is None:
        if channel is not None and asset is not None:
            raise HTTPException(
                status_code=404,
                detail="No signal has been published for this channel, asset, and date",
            )
        raise HTTPException(status_code=404, detail="No signal has been published yet")

    if not can_read(reader, signal.channel, signal.asset):
        raise HTTPException(
            status_code=403,
            detail="Reader is not allowed to access this signal",
        )

    logger.info(
        "signal_read account=%s channel=%s asset=%s as_of_date=%s",
        reader.account,
        signal.channel,
        signal.asset,
        signal.as_of_date,
    )
    return signal