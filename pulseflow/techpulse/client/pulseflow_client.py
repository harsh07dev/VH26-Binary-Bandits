"""PulseFlow module: pulseflow_client.

Async HTTP transport layer for TechPulse.

Bridges the TrafficGenerator (via its EventSink interface) to Machine Two's
bulk ingestion endpoint:

    POST {base_url}/events
    Content-Type: application/json
    Body: {"events": [...]}   ← serialised EventBatch

Architecture position:
    TrafficGenerator ──(EventSink)──► PulseFlowClient ──(HTTP)──► Machine Two /events

Design decisions:
  • Uses httpx.AsyncClient for full async I/O with HTTP/1.1 keep-alive pooling.
  • One AsyncClient is created in start() / lazily on first send, reused for all
    subsequent batches – no per-batch connection overhead.
  • send_batch() is a plain coroutine (no asyncio.create_task); the generator
    awaits it directly, providing natural back-pressure.
  • Non-2xx responses raise PulseFlowClientError so TrafficGenerator can count them.
  • Repeated close() calls are safe (idempotent).
  • received_at is never set; Machine Two owns ingestion timestamps.
"""

import logging
from typing import Optional

import httpx

from contracts.events import EventBatch
from techpulse.config import DEFAULT_HTTP_TIMEOUT, PIPELINE_BASE_URL

logger = logging.getLogger(__name__)

# Path that Machine Two's ingestion endpoint listens on.
_EVENTS_PATH = "/events/batch"


class PulseFlowClientError(Exception):
    """Raised when the PulseFlow pipeline returns an error or is unreachable."""


class PulseFlowClient:
    """Async HTTP client that sends EventBatch objects to the PulseFlow pipeline.

    Intended lifecycle::

        client = PulseFlowClient(base_url="http://127.0.0.1:8000")
        await client.start()
        try:
            generator = TrafficGenerator(..., sink=client.send_batch)
            await generator.start()
            ...
        finally:
            await generator.stop()
            await client.close()

    ``send_batch`` can also be called without an explicit ``start()``;
    the underlying HTTP client is initialised lazily on the first call.
    """

    def __init__(
        self,
        base_url: str = PIPELINE_BASE_URL,
        timeout: float = DEFAULT_HTTP_TIMEOUT,
    ) -> None:
        """Initialise the client.

        Args:
            base_url: Root URL of the PulseFlow pipeline server.
                      A trailing slash or ``/events`` suffix is stripped
                      automatically to avoid double-slash paths.
            timeout:  HTTP request timeout in seconds.  Applies to connection,
                      read, and write phases combined.
        """
        # Normalise: strip trailing slash so path concatenation is clean.
        self._base_url: str = base_url.rstrip("/")
        self._timeout: float = timeout
        self._events_url: str = f"{self._base_url}{_EVENTS_PATH}"
        self._client: Optional[httpx.AsyncClient] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Initialise the underlying HTTP client and its connection pool.

        Safe to call multiple times – subsequent calls are no-ops.
        """
        if self._client is None:
            self._client = self._make_client()
            logger.info("PulseFlowClient started → %s", self._events_url)

    async def close(self) -> None:
        """Gracefully close the HTTP client and release connections.

        Safe to call multiple times (idempotent).
        """
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            logger.info("PulseFlowClient closed.")

    # ------------------------------------------------------------------
    # EventSink interface
    # ------------------------------------------------------------------

    async def send_batch(self, batch: EventBatch) -> None:
        """POST an EventBatch to Machine Two's /events endpoint.

        This is the ``EventSink`` callable consumed by TrafficGenerator::

            generator = TrafficGenerator(..., sink=client.send_batch)

        Args:
            batch: The batch of events to send.

        Raises:
            PulseFlowClientError: On connection failure, timeout, or non-2xx response.
        """
        # Lazy initialisation: start() is recommended but not mandatory.
        if self._client is None:
            await self.start()

        # Serialise using Pydantic v2 API.  model_dump_json() produces the
        # canonical JSON string matching the shared EventBatch contract fields.
        body: str = batch.model_dump_json()

        try:
            response = await self._client.post(
                self._events_url,
                content=body,
                headers={"Content-Type": "application/json"},
            )
        except httpx.TimeoutException as exc:
            raise PulseFlowClientError(
                f"Timeout sending batch of {len(batch)} events to {self._events_url}: {exc}"
            ) from exc
        except httpx.ConnectError as exc:
            raise PulseFlowClientError(
                f"Connection error sending batch to {self._events_url}: {exc}"
            ) from exc
        except httpx.RequestError as exc:
            raise PulseFlowClientError(
                f"HTTP request error sending batch to {self._events_url}: {exc}"
            ) from exc

        if response.status_code < 200 or response.status_code >= 300:
            raise PulseFlowClientError(
                f"Pipeline returned HTTP {response.status_code} for batch of "
                f"{len(batch)} events. Body: {response.text[:200]}"
            )

        logger.debug(
            "Sent batch of %d events → HTTP %d", len(batch), response.status_code
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_client(self) -> httpx.AsyncClient:
        """Create a configured httpx.AsyncClient with pooling and timeouts."""
        return httpx.AsyncClient(
            timeout=httpx.Timeout(self._timeout),
            # httpx uses HTTP/1.1 keep-alive by default; no extra config needed.
        )
