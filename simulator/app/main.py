import asyncio
import hashlib
import hmac
import json as json_module
import os
import random
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

app = FastAPI(title="Xeno Channel Simulator", version="1.1.0")
CRM_WEBHOOK_URL = os.getenv("CRM_WEBHOOK_URL", "http://localhost:8000/api/v1/webhooks/channel-events")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "webhook-secret-change-me")
REDIS_URL = os.getenv("REDIS_URL", "")

# ---------------------------------------------------------------------------
# Redis (optional) – fall back to in-memory lists when unavailable
# ---------------------------------------------------------------------------
_redis_client = None

def _get_redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    if REDIS_URL:
        try:
            import redis
            _redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
            _redis_client.ping()
            return _redis_client
        except Exception:
            _redis_client = None
    return None

# In-memory fallback stores
DEAD_LETTERS: list[dict[str, Any]] = []
PROVIDER_EVENTS: list[dict[str, Any]] = []

# ---------------------------------------------------------------------------
# Helpers for dual storage (Redis + in-memory)
# ---------------------------------------------------------------------------
_EVENTS_KEY = "simulator:events"
_DEAD_LETTERS_KEY = "simulator:dead_letters"
_STATS_KEY = "simulator:stats"

def _store_event(event: dict[str, Any]) -> None:
    rc = _get_redis()
    if rc:
        try:
            rc.rpush(_EVENTS_KEY, json_module.dumps(event, default=str))
            rc.ltrim(_EVENTS_KEY, -10000, -1)
            # Update stats counters
            rc.hincrby(_STATS_KEY, "total", 1)
            rc.hincrby(_STATS_KEY, event.get("event_type", "unknown"), 1)
            return
        except Exception:
            pass
    PROVIDER_EVENTS.append(event)

def _store_dead_letter(dl: dict[str, Any]) -> None:
    rc = _get_redis()
    if rc:
        try:
            rc.rpush(_DEAD_LETTERS_KEY, json_module.dumps(dl, default=str))
            rc.ltrim(_DEAD_LETTERS_KEY, -1000, -1)
            return
        except Exception:
            pass
    DEAD_LETTERS.append(dl)

def _get_events(limit: int = 100) -> list[dict[str, Any]]:
    rc = _get_redis()
    if rc:
        try:
            raw = rc.lrange(_EVENTS_KEY, -limit, -1)
            return [json_module.loads(r) for r in raw]
        except Exception:
            pass
    return PROVIDER_EVENTS[-limit:]

def _get_dead_letters(limit: int = 100) -> list[dict[str, Any]]:
    rc = _get_redis()
    if rc:
        try:
            raw = rc.lrange(_DEAD_LETTERS_KEY, -limit, -1)
            return [json_module.loads(r) for r in raw]
        except Exception:
            pass
    return DEAD_LETTERS[-limit:]

def _get_stats() -> dict[str, int]:
    rc = _get_redis()
    if rc:
        try:
            raw = rc.hgetall(_STATS_KEY)
            return {k: int(v) for k, v in raw.items()}
        except Exception:
            pass
    # Build stats from in-memory events
    stats: dict[str, int] = {"total": 0, "delivered": 0, "failed": 0, "opened": 0, "read": 0, "clicked": 0, "converted": 0}
    for ev in PROVIDER_EVENTS:
        et = ev.get("event_type", "unknown")
        stats["total"] += 1
        if et in stats:
            stats[et] += 1
    return stats

# ---------------------------------------------------------------------------
# Channel probability profiles
# ---------------------------------------------------------------------------
CHANNEL_PROFILES = {
    "whatsapp": {"failure": 0.035, "open": 0.72, "click": 0.18, "conversion": 0.045},
    "sms": {"failure": 0.055, "open": 0.50, "click": 0.09, "conversion": 0.025},
    "email": {"failure": 0.025, "open": 0.34, "click": 0.11, "conversion": 0.032},
    "rcs": {"failure": 0.060, "open": 0.48, "click": 0.14, "conversion": 0.036},
}

# ---------------------------------------------------------------------------
# Rate limiter – simple in-memory sliding window (100 msgs/sec)
# ---------------------------------------------------------------------------
_RATE_MAX = int(os.getenv("RATE_LIMIT_PER_SEC", "100"))
_rate_timestamps: list[float] = []

def _check_rate_limit() -> None:
    now = time.monotonic()
    # Prune timestamps older than 1 second
    while _rate_timestamps and _rate_timestamps[0] < now - 1.0:
        _rate_timestamps.pop(0)
    if len(_rate_timestamps) >= _RATE_MAX:
        raise HTTPException(status_code=429, detail="Rate limit exceeded: max 100 messages/second")
    _rate_timestamps.append(now)

# ---------------------------------------------------------------------------
# HMAC webhook signature
# ---------------------------------------------------------------------------
def _sign_payload(payload_bytes: bytes) -> str:
    return hmac.new(WEBHOOK_SECRET.encode(), payload_bytes, hashlib.sha256).hexdigest()

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class ProviderMessage(BaseModel):
    tenant_id: str
    campaign_id: str
    message_id: str
    customer_id: str
    channel: str
    content: dict[str, Any]

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": "channel-simulator"}


@app.post("/provider/messages")
def accept_message(payload: ProviderMessage, background: BackgroundTasks, request: Request):
    _check_rate_limit()
    provider_message_id = f"sim_{uuid.uuid4().hex}"
    request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))
    profile = CHANNEL_PROFILES.get(payload.channel, CHANNEL_PROFILES["sms"])
    background.add_task(simulate_lifecycle, payload.model_dump(), provider_message_id, profile, request_id)
    return {
        "provider_message_id": provider_message_id,
        "request_id": request_id,
        "accepted_at": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/provider/messages/batch")
def accept_batch(payloads: list[ProviderMessage], background: BackgroundTasks, request: Request):
    """Accept a list of messages for batch delivery."""
    results = []
    request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))
    for payload in payloads:
        _check_rate_limit()
        provider_message_id = f"sim_{uuid.uuid4().hex}"
        profile = CHANNEL_PROFILES.get(payload.channel, CHANNEL_PROFILES["sms"])
        background.add_task(simulate_lifecycle, payload.model_dump(), provider_message_id, profile, request_id)
        results.append({
            "provider_message_id": provider_message_id,
            "message_id": payload.message_id,
        })
    return {
        "accepted": len(results),
        "request_id": request_id,
        "results": results,
        "accepted_at": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/provider/events")
def events(limit: int = 100):
    return {"data": _get_events(limit)}


@app.get("/provider/dead-letters")
def dead_letters():
    return {"data": _get_dead_letters(100)}


@app.get("/provider/stats")
def stats():
    """Return aggregate counts: total sent, delivered, failed, opened, clicked, converted."""
    s = _get_stats()
    return {
        "sent": s.get("total", 0),
        "delivered": s.get("delivered", 0),
        "failed": s.get("failed", 0),
        "opened": s.get("opened", 0) + s.get("read", 0),
        "clicked": s.get("clicked", 0),
        "converted": s.get("converted", 0),
    }


# ---------------------------------------------------------------------------
# Lifecycle simulation (background task)
# ---------------------------------------------------------------------------
async def simulate_lifecycle(
    payload: dict[str, Any], provider_message_id: str, profile: dict[str, float], request_id: str
) -> None:
    await asyncio.sleep(random.uniform(0.1, 1.5))
    if random.random() < profile["failure"]:
        await emit(payload, provider_message_id, "failed", {"reason": random.choice(["carrier_reject", "template_rejected", "timeout"])}, request_id)
        _store_dead_letter({"payload": payload, "provider_message_id": provider_message_id, "failed_at": datetime.now(timezone.utc).isoformat()})
        return
    await emit(payload, provider_message_id, "delivered", {"latency_ms": random.randint(150, 4000)}, request_id)
    if random.random() < profile["open"]:
        await asyncio.sleep(random.uniform(0.2, 2.5))
        await emit(payload, provider_message_id, "read" if payload["channel"] in {"whatsapp", "rcs"} else "opened", {}, request_id)
    if random.random() < profile["click"]:
        await asyncio.sleep(random.uniform(0.2, 3.5))
        await emit(payload, provider_message_id, "clicked", {"url": "https://brand.example/campaign"}, request_id)
    if random.random() < profile["conversion"]:
        await asyncio.sleep(random.uniform(0.3, 4.0))
        await emit(payload, provider_message_id, "converted", {"amount": round(random.uniform(399, 7999), 2), "currency": "INR"}, request_id)


@retry(wait=wait_exponential(multiplier=0.5, min=0.5, max=8), stop=stop_after_attempt(4))
async def emit(
    payload: dict[str, Any], provider_message_id: str, event_type: str, metadata: dict[str, Any], request_id: str
) -> None:
    event = {
        "tenant_id": payload["tenant_id"],
        "campaign_id": payload["campaign_id"],
        "message_id": payload["message_id"],
        "customer_id": payload["customer_id"],
        "channel": payload["channel"],
        "event_type": event_type,
        "provider_event_id": f"evt_{uuid.uuid4().hex}",
        "metadata": {"provider_message_id": provider_message_id, **metadata},
    }
    _store_event(event)
    event_bytes = json_module.dumps(event, default=str).encode()
    signature = _sign_payload(event_bytes)
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.post(
            CRM_WEBHOOK_URL,
            content=event_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": signature,
                "X-Request-Id": request_id,
            },
        )
        response.raise_for_status()
