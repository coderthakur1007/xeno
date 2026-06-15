"""Background message-delivery worker.

``MessageWorker`` runs an infinite loop that dequeues payloads from the
``campaign_messages`` Redis queue and delivers them to the channel
simulator via HTTP (with automatic retries).  ``start_worker`` wraps this
in a daemon thread so it can be started alongside the API server.
"""

from __future__ import annotations

import logging
import sys
import threading
from datetime import datetime, timezone
from typing import Any

import httpx
from tenacity import (
    RetryError,
    retry,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import Settings, get_settings
from app.core.redis_client import TaskQueue

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

_handler = logging.StreamHandler(sys.stderr)
_handler.setFormatter(logging.Formatter("%(asctime)s [worker] %(levelname)s %(message)s"))
logger = logging.getLogger("xeno.worker")
logger.addHandler(_handler)
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_QUEUE_NAME = "campaign_messages"
_MAX_RETRIES = 3
_DEQUEUE_TIMEOUT = 5  # seconds


# ---------------------------------------------------------------------------
# MessageWorker
# ---------------------------------------------------------------------------


class MessageWorker:
    """Consumes campaign-message payloads from Redis and delivers them.

    Each payload is POSTed to the channel simulator endpoint configured in
    ``settings.channel_simulator_url``.  Delivery is retried up to
    ``_MAX_RETRIES`` times with exponential back-off.

    Args:
        db_session_factory: A callable (typically ``SessionLocal``) that
            returns a new SQLAlchemy ``Session``.
        settings: Application settings instance.
    """

    def __init__(
        self,
        db_session_factory: Any,
        settings: Settings | None = None,
    ) -> None:
        self._session_factory = db_session_factory
        self._settings = settings or get_settings()
        self._queue = TaskQueue()
        self._running = True

    # -- Delivery with retry ------------------------------------------------

    @staticmethod
    @retry(
        stop=stop_after_attempt(_MAX_RETRIES),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
        reraise=True,
    )
    def _post(url: str, payload: dict[str, Any]) -> httpx.Response:
        """POST *payload* to *url* with automatic retries.

        Raises:
            httpx.HTTPStatusError: On 4xx / 5xx responses after retries.
            httpx.RequestError: On network-level failures after retries.
        """
        with httpx.Client(timeout=10) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            return response

    def process_message(self, payload: dict[str, Any]) -> None:
        """Send a single message payload to the channel simulator.

        On permanent failure (after exhausting retries) the error is logged
        but the worker continues processing the next message.
        """
        url = f"{self._settings.channel_simulator_url}/send"
        try:
            self._post(url, payload)
            logger.info(
                "Delivered message %s for campaign %s",
                payload.get("message_id", "?"),
                payload.get("campaign_id", "?"),
            )
        except RetryError:
            logger.error(
                "Permanently failed to deliver message %s after %d attempts",
                payload.get("message_id", "?"),
                _MAX_RETRIES,
            )
        except httpx.HTTPStatusError as exc:
            logger.error(
                "HTTP %s delivering message %s: %s",
                exc.response.status_code,
                payload.get("message_id", "?"),
                exc.response.text[:200],
            )
        except httpx.RequestError as exc:
            logger.error(
                "Network error delivering message %s: %s",
                payload.get("message_id", "?"),
                exc,
            )

    # -- Main loop ----------------------------------------------------------

    def run(self) -> None:
        """Infinite loop: dequeue → process → repeat.

        Catches all exceptions so the worker never crashes silently.
        """
        logger.info("Worker started — consuming queue '%s'", _QUEUE_NAME)
        while self._running:
            try:
                payload = self._queue.dequeue(_QUEUE_NAME, timeout=_DEQUEUE_TIMEOUT)
                if payload is None:
                    continue
                self.process_message(payload)
            except Exception:
                logger.exception(
                    "Unhandled error in worker loop at %s",
                    datetime.now(timezone.utc).isoformat(),
                )

    def stop(self) -> None:
        """Signal the worker loop to exit gracefully."""
        self._running = False


# ---------------------------------------------------------------------------
# Helper to start as a daemon thread
# ---------------------------------------------------------------------------


def start_worker(settings: Settings | None = None) -> threading.Thread:
    """Launch a ``MessageWorker`` on a daemon thread.

    The thread will be automatically terminated when the main process exits.

    Args:
        settings: Application settings (resolved lazily if not provided).

    Returns:
        The started ``threading.Thread`` instance.
    """
    if settings is None:
        settings = get_settings()

    # Import here to avoid circular imports at module level
    from app.core.database import SessionLocal

    worker = MessageWorker(db_session_factory=SessionLocal, settings=settings)
    thread = threading.Thread(target=worker.run, name="message-worker", daemon=True)
    thread.start()
    logger.info("Worker daemon thread started (tid=%s)", thread.ident)
    return thread
