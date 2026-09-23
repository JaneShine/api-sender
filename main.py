import os
import secrets
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Signal Feed API", version="0.1.0")

PUBLISH_API_KEY = os.environ.get("PUBLISH_API_KEY", "")
READ_API_KEYS = {key.strip() for key in os.environ.get("READ_API_KEYS", "").split(",") if key.strip()}


class SignalIn(BaseModel):
    channel: str
    asset: str
    signal: str
    value: float | None = None
    confidence: float | None = None
    source: str | None = None
    expires_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SignalOut(SignalIn):
    id: str
    published_at: datetime


latest_signal: SignalOut | None = None


def extract_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    scheme, separator, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not separator or not token.strip():
        raise HTTPException(status_code=401, detail="Authorization must use Bearer token")
    return token.strip()


def require_reader(authorization: str | None) -> None:
    token = extract_token(authorization)
    if not any(secrets.compare_digest(token, key) for key in READ_API_KEYS):
        raise HTTPException(status_code=403, detail="Invalid read API key")


def require_publisher(authorization: str | None) -> None:
    token = extract_token(authorization)
    if not PUBLISH_API_KEY or not secrets.compare_digest(token, PUBLISH_API_KEY):
        raise HTTPException(status_code=403, detail="Invalid publish API key")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "signal-feed-api"}


@app.post("/v1/publish", response_model=SignalOut)
def publish_signal(signal: SignalIn, authorization: str | None = Header(default=None)) -> SignalOut:
    global latest_signal
    require_publisher(authorization)
    latest_signal = SignalOut(
        **signal.model_dump(),
        id=secrets.token_urlsafe(12),
        published_at=datetime.now(timezone.utc),
    )
    return latest_signal


@app.get("/v1/latest", response_model=SignalOut)
def get_latest_signal(authorization: str | None = Header(default=None)) -> SignalOut:
    require_reader(authorization)
    if latest_signal is None:
        raise HTTPException(status_code=404, detail="No signal has been published yet")
    return latest_signal
