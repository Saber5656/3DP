import unittest
from inspect_slice import crosses_vertical_passage

class TopPassageTests(unittest.TestCase):
    def test_crossing_segment_with_both_endpoints_outside(self):
        self.assertTrue(crosses_vertical_passage([[-3,0],[3,0]], 5, [0,0], [3,7]))
    def test_outside_axial_range_or_radius_is_not_a_crossing(self):
        self.assertFalse(crosses_vertical_passage([[-3,0],[3,0]], 8, [0,0], [3,7]))
        self.assertFalse(crosses_vertical_passage([[-3,1.1],[3,1.1]], 5, [0,0], [3,7]))
