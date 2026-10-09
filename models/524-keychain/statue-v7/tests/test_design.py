"""Regression requirements from the completed v6 print, before building v7."""
import importlib.util
from pathlib import Path

import manifold3d as m
import numpy as np
import unittest

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("keychain_v7", ROOT / "build.py")
design = importlib.util.module_from_spec(spec)
spec.loader.exec_module(design)


class DesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = design.build_model()

    def test_successful_statue_body_and_front_surface_are_preserved(self):
        model = self.model
        previous = design.previous.build_model()
        assert (model["character"] - previous["character"]).volume() < 1e-7
        assert (previous["character"] - model["character"]).volume() < 1e-7
        assert np.allclose(design.as_mesh(model["character"]).extents,
                           [150*40/153, 85*40/153, 40])


    def test_successful_color_layers_and_yellow_backing_are_preserved(self):
        model = self.model
        parts = model["parts"]
        self.assertAlmostEqual(sum(s.volume() for s in parts.values()), model["full"].volume(), delta=.002)
        for i, (name, solid) in enumerate(parts.items()):
            mesh = design.as_mesh(solid)
            assert mesh.is_watertight and mesh.is_winding_consistent, name
            for other in list(parts.values())[i+1:]:
                assert (solid ^ other).volume() < .001
        previous = design.previous.build_model()
        for name in ("white", "orange", "teal"):
            # The successful printed colors depend on actual depth/overlap,
            # especially translucent blue over yellow. Preserve both boundaries.
            self.assertLess((parts[name] - previous["parts"][name]).volume(), .001, name)
            self.assertLess((previous["parts"][name] - parts[name]).volume(), .001, name)
        yellow = parts['yellow'] ^ model['character']
        old_yellow = previous['parts']['yellow'] ^ previous['character']
        self.assertLess((yellow-old_yellow).volume(), .001)
        self.assertLess((old_yellow-yellow).volume(), .001)


    def test_hook_stays_top_center_perpendicular_and_passes_real_gauge(self):
        model = self.model
        cx, cy, cz = model["eyelet_center"]
        assert (cx, cy) == (0, 0)
        self.assertAlmostEqual(cz, 40.8)
        gauge = m.Manifold.cylinder(4.2, 1.2, circular_segments=96).rotate([0,90,0]).translate([-2.1,0,cz])
        assert (gauge ^ model["full"]).volume() < .0001
        self.assertAlmostEqual(design.as_mesh(model["eyelet"]).extents[0], 2.4)
        assert len(design.as_mesh(model["full"]).split()) == 1
        assert model["root_overlap_mm3"] > 10
        assert model["connector_eyelet_overlap_mm3"] > 3
        assert design.as_mesh(model["full"]).bounds[1,2] <= 44.61


    def test_loop_has_flat_supported_underside_and_45_degree_hole_roof(self):
        outer, inner = design.loop_contours()
        bottom = outer[abs(outer[:,1] - outer[:,1].min()) < 1e-6]
        assert np.ptp(bottom[:,0]) >= 4.0
        # In print coordinates the hole roof slopes inward at no more than 45 degrees.
        apex = inner[np.argmax(inner[:,1])]
        tangencies = inner[[0,-2]]
        for point in tangencies:
            assert abs(apex[0]-point[0]) <= apex[1]-point[1] + 1e-6
        assert outer[:,1].min() <= inner[:,1].min() - 1.59


    def test_coupon_preserves_loop_height_above_bed_and_hole_clearance(self):
        model = self.model
        full = design.orient_for_print(model["parts"])
        coupon = design.coupon_for_print()
        ring = model["eyelet"].rotate([-90,0,0]).translate([0,0,model["rear_mm"]])
        assert (ring - coupon).volume() < .0001
        self.assertAlmostEqual(coupon.bounding_box()[2], 0)
        assert (coupon - full["yellow"]).volume() < .0001
        blocker = next(iter(design.support_blockers_for_print().values()))
        # The block must leave the first flat underside supportable.
        low = m.Manifold.cube([10,12,.2]).translate([-5,35,ring.bounding_box()[2]])
        assert (blocker ^ low).volume() < .0001

if __name__ == "__main__":
    unittest.main()
