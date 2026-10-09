"""Regression: a successful slicer exit must not hide a tower collision warning."""
import unittest


class SliceWarningTests(unittest.TestCase):
    def test_rejects_tower_collision_warning_even_without_error(self):
        from inspect_slice import verify_slice_warnings
        with self.assertRaisesRegex(ValueError, 'Prime Tower'):
            verify_slice_warnings([
                '[warning] Prime Tower is too close to others, and collisions may be caused.'
            ])

    def test_accepts_informational_support_warning(self):
        from inspect_slice import verify_slice_warnings
        verify_slice_warnings(['[warning] tree support default to organic support'])
