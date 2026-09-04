"""Unit tests for TechPulse PulseFlowClient.

Strategy
--------
* Uses ``unittest.IsolatedAsyncioTestCase`` (stdlib, Python 3.8+) for async
  test methods – no pytest-asyncio required.
* The real httpx.AsyncClient is replaced with a lightweight mock so tests
  never attempt live HTTP connections.
* All assertions verify the client behaviour spec without touching contracts.
"""

import json
import unittest
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch, call

import httpx

from contracts.events import EventBatch
from techpulse.generator.event_factory import EventFactory
from techpulse.client.pulseflow_client import PulseFlowClient, PulseFlowClientError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_batch(n: int = 3) -> EventBatch:
    """Create a small EventBatch for testing."""
    factory = EventFactory(seed=0)
    return factory.create_events(n)


def _ok_response(status: int = 200, body: str = '{"status":"ok"}') -> MagicMock:
    """Build a mock httpx.Response with a 2xx status."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.text = body
    return resp


def _error_response(status: int = 500, body: str = "Internal Server Error") -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.text = body
    return resp


def _make_client_with_mock(
    base_url: str = "http://127.0.0.1:8000",
    mock_response: Optional[MagicMock] = None,
    side_effect=None,
) -> tuple[PulseFlowClient, MagicMock]:
    """Return (PulseFlowClient, mock_http_client) with post() pre-configured."""
    mock_http = AsyncMock(spec=httpx.AsyncClient)
    mock_http.aclose = AsyncMock()

    if side_effect is not None:
        mock_http.post = AsyncMock(side_effect=side_effect)
    else:
        mock_http.post = AsyncMock(return_value=mock_response or _ok_response())

    client = PulseFlowClient(base_url=base_url, timeout=5.0)
    client._client = mock_http   # inject mock; bypasses start()
    return client, mock_http


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPulseFlowClientLifecycle(unittest.IsolatedAsyncioTestCase):

    async def test_start_creates_http_client(self):
        client = PulseFlowClient(base_url="http://test.local:8000")
        self.assertIsNone(client._client)
        await client.start()
        self.assertIsNotNone(client._client)
        await client.close()

    async def test_repeated_start_is_noop(self):
        client = PulseFlowClient(base_url="http://test.local:8000")
        await client.start()
        first = client._client
        await client.start()          # second call must not replace the client
        self.assertIs(client._client, first)
        await client.close()

    async def test_close_releases_client(self):
        client, mock_http = _make_client_with_mock()
        await client.close()
        mock_http.aclose.assert_called_once()
        self.assertIsNone(client._client)

    async def test_repeated_close_is_safe(self):
        client, mock_http = _make_client_with_mock()
        await client.close()
        await client.close()   # second close must not raise
        mock_http.aclose.assert_called_once()   # only closed once


class TestPulseFlowClientHTTPBehaviour(unittest.IsolatedAsyncioTestCase):

    async def test_correct_post_url(self):
        client, mock_http = _make_client_with_mock(base_url="http://127.0.0.1:9000")
        batch = _make_batch()
        await client.send_batch(batch)

        posted_url = mock_http.post.call_args.args[0]
        self.assertEqual(posted_url, "http://127.0.0.1:9000/events")

    async def test_no_double_slash_in_url(self):
        """Base URL with trailing slash must not produce //events."""
        client, mock_http = _make_client_with_mock(base_url="http://127.0.0.1:8000/")
        await client.send_batch(_make_batch())
        posted_url = mock_http.post.call_args.args[0]
        self.assertNotIn("//events", posted_url)
        self.assertTrue(posted_url.endswith("/events"))

    async def test_correct_json_shape(self):
        """Request body must be {"events": [...]} (EventBatch schema)."""
        client, mock_http = _make_client_with_mock()
        batch = _make_batch(5)
        await client.send_batch(batch)

        body_bytes = mock_http.post.call_args.kwargs.get("content") or \
                     mock_http.post.call_args.args[1] if len(mock_http.post.call_args.args) > 1 else \
                     mock_http.post.call_args.kwargs["content"]
        parsed = json.loads(body_bytes)
        self.assertIn("events", parsed)
        self.assertIsInstance(parsed["events"], list)
        self.assertEqual(len(parsed["events"]), 5)

    async def test_content_type_header(self):
        client, mock_http = _make_client_with_mock()
        await client.send_batch(_make_batch())
        headers = mock_http.post.call_args.kwargs.get("headers", {})
        self.assertEqual(headers.get("Content-Type"), "application/json")

    async def test_event_batch_serialisation_preserves_fields(self):
        """All shared Event fields appear in the serialised JSON body."""
        client, mock_http = _make_client_with_mock()
        batch = _make_batch(1)
        await client.send_batch(batch)

        body_bytes = mock_http.post.call_args.kwargs["content"]
        parsed = json.loads(body_bytes)
        event_json = parsed["events"][0]

        for field in ("event_id", "event_type", "timestamp", "payload", "priority", "received_at"):
            self.assertIn(field, event_json, f"Field '{field}' missing from serialised event")

    async def test_received_at_is_not_set_by_techpulse(self):
        """TechPulse must never populate received_at; Machine Two owns it."""
        client, mock_http = _make_client_with_mock()
        batch = _make_batch(3)
        await client.send_batch(batch)

        body_bytes = mock_http.post.call_args.kwargs["content"]
        parsed = json.loads(body_bytes)
        for event_json in parsed["events"]:
            self.assertIsNone(event_json["received_at"],
                              "received_at must be null – only Machine Two sets it")

    async def test_multiple_batches_reuse_same_http_client(self):
        """The same AsyncClient instance handles all sequential batches."""
        client, mock_http = _make_client_with_mock()
        for _ in range(4):
            await client.send_batch(_make_batch(2))
        # post() was called 4 times on the SAME mock – no new client created.
        self.assertEqual(mock_http.post.call_count, 4)

    async def test_one_post_per_batch_not_per_event(self):
        """A batch of N events must result in exactly 1 HTTP POST."""
        client, mock_http = _make_client_with_mock()
        batch = _make_batch(10)
        await client.send_batch(batch)
        self.assertEqual(mock_http.post.call_count, 1)

    async def test_successful_response(self):
        client, _ = _make_client_with_mock(mock_response=_ok_response(202))
        # Must not raise
        await client.send_batch(_make_batch())


class TestPulseFlowClientErrorHandling(unittest.IsolatedAsyncioTestCase):

    async def test_non_2xx_raises_client_error(self):
        client, _ = _make_client_with_mock(mock_response=_error_response(500))
        with self.assertRaises(PulseFlowClientError) as ctx:
            await client.send_batch(_make_batch())
        self.assertIn("500", str(ctx.exception))

    async def test_404_raises_client_error(self):
        client, _ = _make_client_with_mock(mock_response=_error_response(404, "Not Found"))
        with self.assertRaises(PulseFlowClientError):
            await client.send_batch(_make_batch())

    async def test_timeout_raises_client_error(self):
        client, _ = _make_client_with_mock(side_effect=httpx.TimeoutException("timed out"))
        with self.assertRaises(PulseFlowClientError) as ctx:
            await client.send_batch(_make_batch())
        self.assertIn("Timeout", str(ctx.exception))

    async def test_connect_error_raises_client_error(self):
        client, _ = _make_client_with_mock(side_effect=httpx.ConnectError("refused"))
        with self.assertRaises(PulseFlowClientError) as ctx:
            await client.send_batch(_make_batch())
        self.assertIn("Connection error", str(ctx.exception))

    async def test_generic_request_error_raises_client_error(self):
        client, _ = _make_client_with_mock(side_effect=httpx.RequestError("generic"))
        with self.assertRaises(PulseFlowClientError):
            await client.send_batch(_make_batch())


class TestPulseFlowClientLazyInit(unittest.IsolatedAsyncioTestCase):

    async def test_send_batch_without_explicit_start(self):
        """send_batch() initialises the HTTP client lazily if start() wasn't called."""
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.aclose = AsyncMock()
        mock_http.post = AsyncMock(return_value=_ok_response())

        client = PulseFlowClient(base_url="http://127.0.0.1:8000")
        # Patch _make_client to inject our mock
        with patch.object(client, "_make_client", return_value=mock_http):
            await client.send_batch(_make_batch())

        self.assertIsNotNone(client._client)
        await client.close()


if __name__ == "__main__":
    unittest.main()
