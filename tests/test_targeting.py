import unittest
from hardware.targeting import Alignment, plan_pointing, suggest_direction

class TargetingTests(unittest.TestCase):
    def setUp(self):
        # Illustrative calibration only; not a physical AstroLocator calibration.
        self.cal = Alignment('E', 400 / 45, 1, 1325, (1975 - 1325) / 90)

    def test_cardinal_suggestion(self):
        self.assertEqual(suggest_direction(82), 'E')
        self.assertEqual(suggest_direction(355), 'N')

    def test_center_target(self):
        p = plan_pointing(90, 0, self.cal)
        self.assertTrue(p.reachable)
        self.assertEqual(p.azimuth_pulse, 1500)
        self.assertEqual(p.altitude_pulse, 1325)

    def test_outside_azimuth_has_no_commands(self):
        p = plan_pointing(180, 20, self.cal)
        self.assertFalse(p.reachable)
        self.assertIsNone(p.azimuth_pulse)
        self.assertIsNone(p.altitude_pulse)

    def test_outside_altitude_has_no_commands(self):
        p = plan_pointing(90, 90, Alignment('E', 400/45, 1, 1900, 7))
        self.assertFalse(p.reachable)
        self.assertIsNone(p.azimuth_pulse)
        self.assertIsNone(p.altitude_pulse)

    def test_below_horizon(self):
        self.assertFalse(plan_pointing(90, -2, self.cal).reachable)

    def test_wraparound(self):
        cal = Alignment('N', 400/45, 1, 1325, 7)
        self.assertTrue(plan_pointing(355, 10, cal).reachable)

if __name__ == '__main__':
    unittest.main()
