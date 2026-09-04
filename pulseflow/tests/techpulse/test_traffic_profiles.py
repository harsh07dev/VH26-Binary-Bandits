"""Unit tests for TechPulse traffic profiles."""

import unittest
import random
from techpulse.generator.traffic_profiles import (
    TrafficProfile,
    SteadyProfile,
    RampProfile,
    SurgeProfile,
    HarmonicProfile
)

class TestTrafficProfiles(unittest.TestCase):
    
    def test_steady_profile(self):
        profile = SteadyProfile("steady", baseline_rate=100.0)
        self.assertEqual(profile.target_rate(0.0), 100.0)
        self.assertEqual(profile.target_rate(10.0), 100.0)
        self.assertEqual(profile.target_rate(1000.0), 100.0)

    def test_ramp_profile(self):
        profile = RampProfile("ramp", baseline_rate=100.0, target_rate=1000.0, duration=30.0)
        self.assertEqual(profile.target_rate(0.0), 100.0)
        self.assertEqual(profile.target_rate(-5.0), 100.0)
        self.assertEqual(profile.target_rate(15.0), 550.0)
        self.assertEqual(profile.target_rate(30.0), 1000.0)
        self.assertEqual(profile.target_rate(40.0), 1000.0)

    def test_surge_profile(self):
        profile = SurgeProfile("surge_20x", baseline_rate=100.0, multiplier=20.0)
        self.assertEqual(profile.target_rate(0.0), 2000.0)
        self.assertEqual(profile.target_rate(50.0), 2000.0)

    def test_harmonic_profile(self):
        profile = HarmonicProfile("harmonic", baseline_rate=100.0, amplitude=0.5, period=10.0)
        self.assertAlmostEqual(profile.target_rate(0.0), 100.0)
        self.assertAlmostEqual(profile.target_rate(2.5), 150.0) # sin(pi/2) = 1
        self.assertAlmostEqual(profile.target_rate(5.0), 100.0) # sin(pi) = 0
        self.assertAlmostEqual(profile.target_rate(7.5), 50.0) # sin(3pi/2) = -1
        self.assertAlmostEqual(profile.target_rate(10.0), 100.0) # sin(2pi) = 0
        
        # Test non-negativity constraint
        with self.assertRaises(ValueError):
            HarmonicProfile("invalid", baseline_rate=100.0, amplitude=1.1, period=10.0)
            
    def test_event_distribution(self):
        custom_dist = {"ORDER": 1.0, "CLICK": 0.0}
        profile = SteadyProfile("dist", baseline_rate=10.0, event_distribution=custom_dist)
        
        rng = random.Random(42)
        event_type = profile.get_event_type(rng)
        self.assertEqual(event_type, "ORDER")
        
        # Check defaults
        default_profile = SteadyProfile("default", baseline_rate=10.0)
        event_type = default_profile.get_event_type(rng)
        self.assertIn(event_type, TrafficProfile.DEFAULT_DISTRIBUTION.keys())

    def test_invalid_configurations(self):
        with self.assertRaises(ValueError):
            SteadyProfile("invalid", baseline_rate=-10.0)
            
        with self.assertRaises(ValueError):
            RampProfile("invalid", baseline_rate=10.0, target_rate=-5.0, duration=10.0)
            
        with self.assertRaises(ValueError):
            RampProfile("invalid", baseline_rate=10.0, target_rate=50.0, duration=-10.0)
            
        with self.assertRaises(ValueError):
            SurgeProfile("invalid", baseline_rate=10.0, multiplier=-5.0)
            
        with self.assertRaises(ValueError):
            HarmonicProfile("invalid", baseline_rate=10.0, amplitude=0.5, period=-10.0)
            
        with self.assertRaises(ValueError):
            SteadyProfile("invalid", baseline_rate=10.0, event_distribution={"A": -1.0})
            
        with self.assertRaises(ValueError):
            SteadyProfile("invalid", baseline_rate=10.0, event_distribution={})

    def test_deterministic_target_rate(self):
        profile = HarmonicProfile("harmonic", baseline_rate=100.0, amplitude=0.5, period=10.0)
        rate1 = profile.target_rate(1.234)
        rate2 = profile.target_rate(1.234)
        self.assertEqual(rate1, rate2)

if __name__ == '__main__':
    unittest.main()
