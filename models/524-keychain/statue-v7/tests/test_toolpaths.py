import importlib.util
from pathlib import Path
import unittest
import numpy as np

spec = importlib.util.spec_from_file_location('paths',Path(__file__).parents[1]/'verify_paths.py')
paths = importlib.util.module_from_spec(spec)
spec.loader.exec_module(paths)


class MotionTests(unittest.TestCase):
    def test_actual_low_tower_z_is_not_overwritten_by_object_layer_comment(self):
        code = ('M83\nG90\nG1 Z20 X0 Y0\n; CHANGE_LAYER\n; Z_HEIGHT: 20.08\n'
                '; FEATURE: Prime tower\nG1 Z.2\nG1 X10 E1\n')
        result = list(paths.segments(code))
        self.assertEqual(len(result),1)
        np.testing.assert_allclose(result[0]['points'][:,2],.2)

    def test_arc_is_sampled_and_pure_recovery_omitted(self):
        code = ('M83\nG1 X5 Y0 Z1\n; CHANGE_LAYER\n; FEATURE: Outer wall\n'
                'G1 E.8\nG2 X5 Y0 I-2 J0 E1\n')
        result = list(paths.segments(code))
        self.assertEqual(len(result),1)
        self.assertGreater(len(result[0]['points']),20)
        self.assertGreater(np.ptp(result[0]['points'][:,1]),3.9)


if __name__ == '__main__':
    unittest.main()
