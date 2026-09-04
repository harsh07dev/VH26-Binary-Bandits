"""Unit tests for TechPulse main entrypoint."""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from techpulse import config
from techpulse.main import _build_profile, _run_techpulse
from techpulse.generator.traffic_profiles import SteadyProfile, RampProfile, SurgeProfile, HarmonicProfile


class TestMainOrchestration(unittest.IsolatedAsyncioTestCase):
    
    def setUp(self):
        # Override config for predictable tests
        self._orig_profile = config.TECHPULSE_PROFILE
        self._orig_rate = config.TECHPULSE_RATE
        self._orig_batch = config.TECHPULSE_BATCH_SIZE
        
        config.TECHPULSE_PROFILE = "steady"
        config.TECHPULSE_RATE = 100.0
        config.TECHPULSE_BATCH_SIZE = 10

    def tearDown(self):
        # Restore config
        config.TECHPULSE_PROFILE = self._orig_profile
        config.TECHPULSE_RATE = self._orig_rate
        config.TECHPULSE_BATCH_SIZE = self._orig_batch

    def test_build_profile_steady(self):
        config.TECHPULSE_PROFILE = "steady"
        profile = _build_profile()
        self.assertIsInstance(profile, SteadyProfile)
        self.assertEqual(profile.baseline_rate, 100.0)

    def test_build_profile_ramp(self):
        config.TECHPULSE_PROFILE = "ramp"
        profile = _build_profile()
        self.assertIsInstance(profile, RampProfile)

    def test_build_profile_surge(self):
        config.TECHPULSE_PROFILE = "surge"
        profile = _build_profile()
        self.assertIsInstance(profile, SurgeProfile)

    def test_build_profile_harmonic(self):
        config.TECHPULSE_PROFILE = "harmonic"
        profile = _build_profile()
        self.assertIsInstance(profile, HarmonicProfile)

    def test_build_profile_invalid_raises(self):
        config.TECHPULSE_PROFILE = "invalid_profile"
        with self.assertRaises(ValueError):
            _build_profile()

    @patch("techpulse.main.PulseFlowClient")
    @patch("techpulse.main.TrafficGenerator")
    @patch("techpulse.main.asyncio.Event")
    async def test_run_techpulse_orchestration(self, mock_event_cls, mock_generator_cls, mock_client_cls):
        """Test that components are wired correctly and started/stopped."""
        # Setup mocks
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client
        
        mock_generator = AsyncMock()
        # Mock stats (synchronous method)
        mock_stats = MagicMock()
        mock_stats.events_generated = 100
        mock_stats.batches_generated = 10
        mock_stats.errors = 0
        mock_generator.stats = MagicMock(return_value=mock_stats)
        mock_generator_cls.return_value = mock_generator

        mock_event = AsyncMock()
        mock_event_cls.return_value = mock_event

        # Execute
        await _run_techpulse()

        # Verify Client instantiated
        mock_client_cls.assert_called_once_with(base_url=config.PIPELINE_BASE_URL)
        
        # Verify Generator instantiated with correct sink
        mock_generator_cls.assert_called_once()
        kwargs = mock_generator_cls.call_args.kwargs
        self.assertEqual(kwargs['batch_size'], 10)
        self.assertEqual(kwargs['sink'], mock_client.send_batch)
        self.assertIsInstance(kwargs['profile'], SteadyProfile)
        
        # Verify Start sequence
        mock_client.start.assert_awaited_once()
        mock_generator.start.assert_awaited_once()
        
        # Verify Stop sequence happens after event wait
        mock_event.wait.assert_awaited_once()
        mock_generator.stop.assert_awaited_once()
        mock_client.close.assert_awaited_once()

    @patch("techpulse.main._build_profile")
    @patch("techpulse.main.sys.exit")
    async def test_run_techpulse_exits_on_profile_error(self, mock_exit, mock_build):
        """If profile building fails, the process exits cleanly."""
        mock_build.side_effect = ValueError("Bad config")
        mock_exit.side_effect = SystemExit(1)
        
        with self.assertRaises(SystemExit):
            await _run_techpulse()
        
        mock_exit.assert_called_once_with(1)

    @patch("techpulse.main.PulseFlowClient")
    @patch("techpulse.main.TrafficGenerator")
    @patch("techpulse.main.asyncio.Event")
    async def test_run_techpulse_cleans_up_on_cancellation(self, mock_event_cls, mock_generator_cls, mock_client_cls):
        """If wait() is cancelled (e.g. signal), cleanup still happens."""
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client
        
        mock_generator = AsyncMock()
        mock_stats = MagicMock()
        mock_stats.events_generated = 0
        mock_stats.batches_generated = 0
        mock_stats.errors = 0
        mock_generator.stats = MagicMock(return_value=mock_stats)
        mock_generator_cls.return_value = mock_generator

        mock_event = AsyncMock()
        mock_event.wait.side_effect = asyncio.CancelledError()
        mock_event_cls.return_value = mock_event

        await _run_techpulse()

        # Stop should still be called
        mock_generator.stop.assert_awaited_once()
        mock_client.close.assert_awaited_once()

if __name__ == '__main__':
    unittest.main()
