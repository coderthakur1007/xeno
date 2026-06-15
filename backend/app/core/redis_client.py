"""Redis client utilities: caching, rate limiting, and task queue.

Provides a lazy-singleton Redis connection, a JSON-based ``CacheService``,
a sliding-window ``RateLimiter`` backed by Redis sorted sets, and a simple
FIFO ``TaskQueue`` using Redis lists (LPUSH / BRPOP).

All classes degrade gracefully when Redis is unavailable — the rate limiter
allows all requests and the cache returns ``None`` on connection errors.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy singleton Redis connection
# ---------------------------------------------------------------------------

_redis_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    """Return a lazily-initialised Redis connection singleton.

    The connection URL is read from ``settings.redis_url``.  Subsequent calls
    return the same ``redis.Redis`` instance.
    """
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
        )
    return _redis_client


# ---------------------------------------------------------------------------
# CacheService
# ---------------------------------------------------------------------------


class CacheService:
    """Thin JSON cache layer on top of Redis GET/SET."""

    def __init__(self, client: redis.Redis | None = None) -> None:
        self._r = client or get_redis()

    def get(self, key: str) -> Any | None:
        """Retrieve and JSON-deserialise a cached value.

        Returns ``None`` on cache miss or Redis connection failure.
        """
        try:
            raw = self._r.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except redis.ConnectionError:
            logger.warning("Redis connection error in CacheService.get(%s)", key)
            return None
        except (json.JSONDecodeError, TypeError):
            return None

    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        """Serialise *value* as JSON and store with a TTL (seconds)."""
        try:
            self._r.set(key, json.dumps(value, default=str), ex=ttl)
        except redis.ConnectionError:
            logger.warning("Redis connection error in CacheService.set(%s)", key)

    def delete(self, key: str) -> None:
        """Remove a single key from the cache."""
        try:
            self._r.delete(key)
        except redis.ConnectionError:
            logger.warning("Redis connection error in CacheService.delete(%s)", key)

    def invalidate_pattern(self, pattern: str) -> None:
        """Delete all keys matching *pattern* (e.g. ``analytics:*``).

        Uses ``SCAN`` to avoid blocking the server on large key-spaces.
        """
        try:
            cursor: int = 0
            while True:
                cursor, keys = self._r.scan(cursor=cursor, match=pattern, count=200)
                if keys:
                    self._r.delete(*keys)
                if cursor == 0:
                    break
        except redis.ConnectionError:
            logger.warning("Redis connection error in CacheService.invalidate_pattern(%s)", pattern)


# ---------------------------------------------------------------------------
# RateLimiter (sliding window via sorted set)
# ---------------------------------------------------------------------------


class RateLimiter:
    """Sliding-window rate limiter backed by a Redis sorted set.

    Each call to :meth:`check` records the current timestamp and removes
    entries older than *window* seconds.  If the remaining count exceeds
    *limit*, the call returns ``False`` (rate-limited).
    """

    def __init__(self, client: redis.Redis | None = None) -> None:
        self._r = client or get_redis()

    def check(self, key: str, limit: int, window: int) -> bool:
        """Return ``True`` if the request is within the rate limit.

        Args:
            key: Unique identifier for the rate-limit bucket (e.g. user ID).
            limit: Maximum allowed requests within *window* seconds.
            window: Sliding window size in seconds.

        Returns:
            ``True`` if allowed, ``False`` if rate-limited.
            On Redis connection failure, defaults to *allow*.
        """
        try:
            now = time.time()
            pipeline = self._r.pipeline(transaction=True)
            # Remove entries outside the window
            pipeline.zremrangebyscore(key, 0, now - window)
            # Add current timestamp
            pipeline.zadd(key, {f"{now}": now})
            # Count entries in the window
            pipeline.zcard(key)
            # Set key expiry so stale buckets are cleaned up
            pipeline.expire(key, window)
            results = pipeline.execute()
            current_count: int = results[2]
            return current_count <= limit
        except redis.ConnectionError:
            logger.warning("Redis connection error in RateLimiter.check(%s) — allowing", key)
            return True


# ---------------------------------------------------------------------------
# TaskQueue (Redis list: LPUSH / BRPOP)
# ---------------------------------------------------------------------------


class TaskQueue:
    """Simple FIFO task queue using Redis lists.

    Producers call :meth:`enqueue` (``LPUSH``), consumers call
    :meth:`dequeue` (``BRPOP`` with a timeout).
    """

    def __init__(self, client: redis.Redis | None = None) -> None:
        self._r = client or get_redis()

    def enqueue(self, queue_name: str, payload: dict[str, Any]) -> None:
        """Push *payload* (JSON-serialised) onto the left of *queue_name*."""
        try:
            self._r.lpush(queue_name, json.dumps(payload, default=str))
        except redis.ConnectionError:
            logger.error("Redis connection error in TaskQueue.enqueue(%s)", queue_name)
            raise

    def dequeue(self, queue_name: str, timeout: int = 5) -> dict[str, Any] | None:
        """Blocking pop from the right of *queue_name*.

        Args:
            queue_name: Name of the Redis list to pop from.
            timeout: Seconds to wait for an item (0 = block forever).

        Returns:
            Decoded payload dict, or ``None`` if the timeout elapsed or
            Redis is unreachable.
        """
        try:
            result = self._r.brpop(queue_name, timeout=timeout)
            if result is None:
                return None
            _queue, raw = result
            return json.loads(raw)
        except redis.ConnectionError:
            logger.warning("Redis connection error in TaskQueue.dequeue(%s)", queue_name)
            return None
        except (json.JSONDecodeError, TypeError):
            logger.warning("Invalid JSON popped from queue %s", queue_name)
            return None
