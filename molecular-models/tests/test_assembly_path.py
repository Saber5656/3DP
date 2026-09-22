"""Continuous vertical insertion bounds, including blocked and clear examples."""
import sys
import unittest
from pathlib import Path
import numpy as np
import trimesh

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from verify_assembly import insertion_distance_bound, projected_triangle_distances


class AssemblyPathTests(unittest.TestCase):
    def test_projected_distance_covers_interior_edges_and_degenerate_faces(self):
        triangles=np.array([[[0,0],[2,0],[0,2]],[[3,0],[3,2],[3,1]],[[4,0],[4,0],[4,0]]])
        np.testing.assert_allclose(projected_triangle_distances([.5,.5],triangles),[0,2.5,np.hypot(3.5,.5)])

    def test_base_below_final_centre_allows_insertion(self):
        m=trimesh.creation.box([10,10,2]);m.apply_translation([0,0,-3])
        self.assertAlmostEqual(insertion_distance_bound(m,[0,0,0]),2)

    def test_roof_in_insertion_path_is_blocked(self):
        m=trimesh.creation.box([10,10,2]);m.apply_translation([0,0,8])
        self.assertEqual(insertion_distance_bound(m,[0,0,0]),0)


if __name__=='__main__':unittest.main()
