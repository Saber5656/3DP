import sys
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from inspect_toolpaths import parse_paths


class ToolpathTests(unittest.TestCase):
    def test_records_only_printed_extrusions_and_tracks_layers(self):
        code='M83\nG1 X10 Y10\n; CHANGE_LAYER\n; Z_HEIGHT: 0.2\n; OBJECT_ID: 1\n; FEATURE: Outer wall\nG1 X20 Y10 E1\nG1 X20 Y20\nG1 E-1\n; CHANGE_LAYER\n; Z_HEIGHT: 0.36\nG1 X30 Y20 E1\n'
        paths=parse_paths(code)
        self.assertEqual(len(paths),2);self.assertEqual([x['layer'] for x in paths],[1,2])
        np.testing.assert_allclose(paths[1]['points'],[[20,20],[30,20]])

    def test_counterclockwise_arc_is_not_replaced_with_a_chord(self):
        code='M83\nG1 X1 Y0\n; CHANGE_LAYER\n; Z_HEIGHT: 0.2\n; FEATURE: Outer wall\nG3 X0 Y1 I-1 J0 E1\n'
        xy=parse_paths(code)[0]['points']
        np.testing.assert_allclose(xy[0],[1,0]);np.testing.assert_allclose(xy[-1],[0,1],atol=1e-8)
        np.testing.assert_allclose(np.linalg.norm(xy,axis=1),1,atol=1e-8)
        self.assertGreater(len(xy),3)

    def test_absolute_extrusion_and_reset(self):
        code='M82\nG92 E10\n; CHANGE_LAYER\n; Z_HEIGHT: 0.2\n; FEATURE: Outer wall\nG1 X1 E11\nG1 X2 E10\nG92 E0\nG1 X3 E1\n'
        self.assertEqual(len(parse_paths(code)),2)


if __name__=='__main__':unittest.main()
