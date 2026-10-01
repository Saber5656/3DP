import math
import unittest
import numpy as np


class PrintedBalanceTests(unittest.TestCase):
    def test_weights_only_model_deposition_and_uses_layer_midplane(self):
        from balance import deposited_centroid
        code = '''M83
G1 X0 Y0
; CHANGE_LAYER
; Z_HEIGHT: 2
; LAYER_HEIGHT: 0.2
; FEATURE: Outer wall
G1 X10 Y0 E10
G1 X10 Y10 E30
; FEATURE: Support
G1 X200 Y200 E900
; FEATURE: Custom
G1 X250 Y250 E1000
'''
        result = deposited_centroid(code)
        np.testing.assert_allclose(result['centroid_print_xyz_mm'], [8.75,3.75,1.9])
        self.assertEqual(result['filament_length_mm'], 40)

    def test_semicircle_mass_is_not_at_the_chord_midpoint(self):
        from balance import deposited_centroid
        code = '''M82
G92 E0
G1 X1 Y0
; CHANGE_LAYER
; Z_HEIGHT: 1
; LAYER_HEIGHT: 0.2
; FEATURE: Outer wall
G3 X-1 Y0 I-1 J0 E10
'''
        result = deposited_centroid(code)
        np.testing.assert_allclose(result['centroid_print_xyz_mm'], [0,2/math.pi,.9], atol=.001)

    def test_missing_model_deposition_is_rejected(self):
        from balance import deposited_centroid
        with self.assertRaises(ValueError):
            deposited_centroid('M83\nG1 X10 E10\n')
