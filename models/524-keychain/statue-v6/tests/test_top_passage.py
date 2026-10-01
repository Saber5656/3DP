import unittest
from inspect_slice import crosses_horizontal_passage

class TopPassageTests(unittest.TestCase):
    def test_crossing_segment_with_both_endpoints_outside(self):
        self.assertTrue(crosses_horizontal_passage([[-3,-3],[3,3]], 5, [0,0,5], 2.1))
    def test_outside_axial_range_or_radius_is_not_a_crossing(self):
        self.assertFalse(crosses_horizontal_passage([[-3,0],[3,0]], 6.1, [0,0,5], 2.1))
        self.assertFalse(crosses_horizontal_passage([[3,-3],[3,3]], 5, [0,0,5], 2.1))
    def test_axis_parallel_and_zero_length_segments(self):
        self.assertTrue(crosses_horizontal_passage([[0,-3],[0,3]], 5, [0,0,5], 2.1))
        self.assertTrue(crosses_horizontal_passage([[0,0],[0,0]], 5, [0,0,5], 2.1))
