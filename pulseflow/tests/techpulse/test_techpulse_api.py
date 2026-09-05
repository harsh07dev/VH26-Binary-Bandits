"""Unit tests for TechPulse Control & Telemetry API endpoints."""

import unittest
from fastapi.testclient import TestClient

from contracts.events import EventBatch
from techpulse.app.routes import context, create_app
from techpulse.generator.event_factory import EventFactory
from techpulse.generator.traffic_generator import TrafficGenerator
from techpulse.generator.traffic_profiles import DynamicWorkloadProfile


async def _noop_sink(batch: EventBatch) -> None:
    pass


class TestTechPulseControlAPI(unittest.TestCase):
    """Verify all REST control and telemetry endpoints on port 8001."""

    def setUp(self) -> None:
        self.profile = DynamicWorkloadProfile(baseline_rate=100.0)
        self.factory = EventFactory(seed=1)
        self.generator = TrafficGenerator(self.profile, self.factory, _noop_sink, batch_size=5)
        context.set_instance(self.generator, self.profile, None)
        context.pulseflow_connected = True
        context.pulseflow_latency_ms = 1.4

        self.app = create_app()
        self.client = TestClient(self.app)

    def test_health_check(self) -> None:
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["service"], "techpulse-generator")

    def test_get_metrics(self) -> None:
        res = self.client.get("/metrics")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["state"], "BASELINE")
        self.assertEqual(data["baseline_rate"], 100.0)
        self.assertEqual(data["current_target_rate"], 100.0)
        self.assertTrue(data["pulseflow_connected"])
        self.assertEqual(data["pulseflow_latency_ms"], 1.4)
        self.assertIn("ORDER", data["distribution"])

    def test_control_preset_spike(self) -> None:
        res = self.client.post("/control/preset", json={"multiplier": 20.0, "duration": 30.0})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["target_rate"], 2000.0)
        self.assertEqual(self.profile.target_rate(0.0), 2000.0)

    def test_control_custom_spike(self) -> None:
        res = self.client.post("/control/custom-spike", json={"target_rate": 5000.0, "duration": 15.0})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["target_rate"], 5000.0)
        self.assertEqual(self.profile.target_rate(0.0), 5000.0)

    def test_control_custom_run(self) -> None:
        res = self.client.post("/control/custom-run", json={"total_events": 10000, "max_rate": 2500.0})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["total_events"], 10000)
        self.assertEqual(data["max_rate"], 2500.0)
        self.assertEqual(self.profile.target_rate(0.0), 2500.0)

    def test_control_recover(self) -> None:
        # Trigger spike first
        self.profile.set_preset_spike(20.0)
        self.assertEqual(self.profile.target_rate(0.0), 2000.0)

        # Recover
        res = self.client.post("/control/recover")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["target_rate"], 100.0)
        self.assertEqual(self.profile.target_rate(0.0), 100.0)

    def test_control_reset(self) -> None:
        self.profile.set_custom_spike(5000.0, 15.0)
        res = self.client.post("/control/reset")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.profile.target_rate(0.0), 100.0)

    def test_control_update_distribution(self) -> None:
        new_dist = {
            "ORDER": 20.0,
            "PAYMENT": 20.0,
            "CART_ADD": 25.0,
            "INVENTORY_UPDATE": 15.0,
            "CLICK": 10.0,
            "PAGE_VIEW": 5.0,
            "LOG": 5.0,
        }
        res = self.client.post("/control/distribution", json={"distribution": new_dist})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["distribution"]["ORDER"], 20.0)
        self.assertEqual(self.profile.event_distribution["ORDER"], 20.0)

    def test_control_custom_mix_spike(self) -> None:
        new_dist = {
            "ORDER": 40.0,
            "PAYMENT": 20.0,
            "CART_ADD": 20.0,
            "INVENTORY_UPDATE": 10.0,
            "CLICK": 5.0,
            "PAGE_VIEW": 3.0,
            "LOG": 2.0,
        }
        res = self.client.post(
            "/control/custom-mix-spike",
            json={
                "target_rate": 3500.0,
                "duration": 25.0,
                "distribution": new_dist,
                "preset_id": "custom",
                "preset_label": "Custom Workload Mix",
            },
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["target_rate"], 3500.0)
        self.assertEqual(data["distribution"]["ORDER"], 40.0)
        self.assertEqual(self.profile.distribution_preset, "custom")
        self.assertEqual(self.profile.target_rate(0.0), 3500.0)


if __name__ == "__main__":
    unittest.main()
