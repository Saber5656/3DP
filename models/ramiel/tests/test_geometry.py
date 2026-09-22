"""Physical invariants of the actual parametric model, in millimetres."""
import json
import unittest
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import trimesh

from build import build_models, to_mesh, export_3mf

ROOT = Path(__file__).resolve().parents[1]


class GeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = json.loads((ROOT / "design.json").read_text())
        cls.model = build_models(cls.cfg)

    def test_each_print_part_is_one_closed_positive_solid(self):
        for name, solid in self.model["parts"].items():
            with self.subTest(part=name):
                mesh = to_mesh(solid)
                self.assertTrue(mesh.is_watertight)
                self.assertTrue(mesh.is_winding_consistent)
                self.assertGreater(mesh.volume, 0)
                self.assertEqual(sum(c.volume > 0 for c in mesh.split()), 1)
                self.assertGreater(float(mesh.area_faces.min()), 1e-10)

    def test_print_orientation_places_every_part_on_the_bed(self):
        for name, solid in self.model["print_parts"].items():
            with self.subTest(part=name):
                mesh = to_mesh(solid)
                self.assertAlmostEqual(mesh.bounds[0, 2], 0, places=5)
                self.assertGreater(mesh.extents[2], 0.7)

    def test_default_is_one_sharp_octahedron_body(self):
        self.assertNotIn("default_half", self.model["parts"])
        self.assertNotIn("default_pin", self.model["parts"])
        mesh = to_mesh(self.model["parts"]["default_body"])
        np.testing.assert_allclose(mesh.extents, [100 / np.sqrt(2)] * 2 + [100], atol=1e-4)
        outer = [c for c in mesh.split() if c.volume > 0]
        self.assertEqual(len(outer), 1)
        self.assertEqual(len(outer[0].vertices), 6)
        self.assertEqual(len(outer[0].faces), 8)
        self.assertEqual(set(n for n,_ in self.model["assemblies"]["default"]),
                         {"default_body", "default_cradle"})

    def test_default_prints_on_an_edge_without_a_flat_cavity_roof(self):
        mesh = to_mesh(self.model["print_parts"]["default_body"])
        outer = [c for c in mesh.split() if c.volume > 0][0]
        z = outer.vertices[:,2]
        self.assertEqual(int(np.isclose(z,z.min()).sum()), 2)
        self.assertEqual(int(np.isclose(z,z.max()).sum()), 2)
        self.assertAlmostEqual(np.abs(outer.face_normals[:,2]).max(), np.sqrt(2/3), places=7)

    def test_default_cavity_is_empty_and_uniform(self):
        mesh = to_mesh(self.model["parts"]["default_body"])
        h = self.cfg["default_height"] / 2
        a = h / np.sqrt(2)
        inner_a = a - self.cfg["default_wall"] * np.sqrt(1+(a/h)**2)
        expected = 2 * (4*a*a*h - 4*inner_a*inner_a*(inner_a/(a/h))) / 3
        self.assertAlmostEqual(mesh.volume, expected, places=3)
        self.assertEqual(sorted(np.sign(c.volume) for c in mesh.split()), [-1, 1])
        for z in (-45,-25,-1,0,1,25,45):
            self.assertFalse(mesh.contains([[0,0,z],[2,0,z],[0,2,z]]).any())
        # Continuous shell crosses the former equator seam.
        self.assertTrue(mesh.contains([[34.5,0,-.05],[34.5,0,.05]]).all())
        self.assertTrue(mesh.contains([[0,0,-49.5],[0,0,49.5]]).all())

    def test_star_is_one_hollow_body_with_a_spherical_aftermarket_core(self):
        self.assertNotIn("star_front", self.model["parts"])
        self.assertNotIn("star_back", self.model["parts"])
        self.assertNotIn("star_pin", self.model["parts"])
        body = to_mesh(self.model["parts"]["star_body"])
        core = to_mesh(self.model["parts"]["red_core"])
        self.assertAlmostEqual(body.extents[0], self.cfg["star_width"], places=3)
        np.testing.assert_allclose(core.extents, [3, 3, 3], atol=.02)
        self.assertEqual(sorted(np.sign(c.volume) for c in body.split()), [-1, 1])
        self.assertFalse(body.contains([[0,0,-6],[5,0,-6],[-5,0,-6]]).any())
        self.assertLess(body.volume, 50000)
        self.assertEqual(set(n for n,_ in self.model["assemblies"]["star"]),
                         {"star_body", "red_core", "star_base"})

    def test_bead_has_an_open_front_seat_and_solid_bowl_below(self):
        body = to_mesh(self.model["parts"]["star_body"])
        cz = self.cfg["star_bead_center_z"]
        radius = self.cfg["star_core_diameter"] / 2
        self.assertFalse(body.contains([[0,0,cz],[0,0,cz+radius],[radius,0,cz]]).any())
        self.assertTrue(body.contains([[0,0,cz-radius-.8]])[0])

    def test_core_has_five_open_radial_v_valleys(self):
        body = self.model["parts"]["star_body"]
        def front_height(radius, degrees):
            angle = np.deg2rad(degrees)
            xy = radius * np.array([np.cos(angle), np.sin(angle)])
            hits = body.ray_cast([*xy, 80], [*xy, -80])
            self.assertTrue(hits)
            return max(hit.position[2] for hit in hits)
        for degrees in np.arange(5) * 72 - 54:
            # Each groove reaches from the core to the gap between main arms.
            for radius in (10, 20, 25):
                self.assertAlmostEqual(front_height(radius, degrees), 0, places=4)
            # Both adjacent sloping faces rise away from the groove centreline.
            for side in (-12, 12):
                self.assertGreater(front_height(12, degrees + side), 4)

    def test_five_quadrangular_arms_project_ahead_of_the_core(self):
        shape = self.model["star_landmarks"]
        self.assertEqual(len(shape["arm_bases"]), 5)
        self.assertEqual(len(shape["front_tips"]), 5)
        core_front = self.cfg["star_bead_center_z"] + self.cfg["star_core_diameter"] / 2
        for root, tip in zip(shape["arm_bases"], shape["front_tips"]):
            q = np.asarray(root)
            self.assertEqual(q.shape, (4, 3))
            self.assertEqual(np.linalg.matrix_rank(q[1:] - q[0], tol=1e-7), 2)
            self.assertGreater(np.linalg.norm(np.cross(q[1]-q[0], q[2]-q[0])), 100)
            self.assertGreater(tip[2] - core_front, 25)

    def test_rear_is_clustered_behind_the_corresponding_arms(self):
        shape = self.model["star_landmarks"]
        self.assertEqual(len(shape["rear_tips"]), 5)
        for front, rear in zip(shape["front_tips"], shape["rear_tips"]):
            f, r = np.asarray(front), np.asarray(rear)
            self.assertLess(np.linalg.norm(r[:2]), np.linalg.norm(f[:2]) * .45)
            self.assertGreater(np.dot(f[:2], r[:2]) / np.linalg.norm(f[:2]) / np.linalg.norm(r[:2]), .99)
            self.assertGreater(r[2], -35)
        self.assertLess(to_mesh(self.model["parts"]["star_body"]).extents[2], 75)

    def test_assembled_parts_do_not_interpenetrate(self):
        for name, pieces in self.model["assemblies"].items():
            for i, (a_name, a) in enumerate(pieces):
                for b_name, b in pieces[i + 1:]:
                    with self.subTest(assembly=name, pair=(a_name, b_name)):
                        self.assertLess((a ^ b).volume(), 0.001)

    def test_city_has_broad_support_candidates_and_leaves_tips_free(self):
        self.assertGreaterEqual(len(self.model["city_buildings"]), 20)
        support = self.model["city_support"]
        self.assertGreater(support["projected_candidate_area_mm2"], 500)
        self.assertGreater(support["shell_com_support_hull_margin_mm"], 5)
        self.assertLess(support["tip_near_contact_count"], 1)
        self.assertGreater(support["contact_x_span_mm"], 35)
        self.assertGreater(support["contact_y_span_mm"], 35)
        broad_patches = [p for p in support["candidate_patches"]
                         if p["projected_candidate_area_mm2"] >= 100]
        self.assertGreaterEqual(len(broad_patches), 3)
        self.assertGreaterEqual(support["nearest_tip_to_contact_mm"], 7.5)
        base = dict(self.model["assemblies"]["star"])["star_base"]
        body = dict(self.model["assemblies"]["star"])["star_body"]
        for rise in [0, .5, 5, 30]:
            self.assertLess((base ^ body.translate([0, 0, rise])).volume(), .001)

    def test_model_sources_do_not_depend_on_absolute_personal_paths(self):
        text = (ROOT / "build.py").read_text()
        self.assertNotIn("/Users/", text)

    def test_3mf_roundtrip_preserves_assembled_pose_and_mm(self):
        for family, pieces in self.model["assemblies"].items():
            with self.subTest(assembly=family), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "assembly.3mf"
                export_3mf(pieces, path)
                loaded = trimesh.load(path, force="scene")
                expected = trimesh.util.concatenate([to_mesh(s) for _, s in pieces])
                np.testing.assert_allclose(loaded.bounds, expected.bounds, atol=1e-4)
                self.assertEqual(len(loaded.geometry), len(pieces))
                with zipfile.ZipFile(path) as z:
                    root = ET.fromstring(z.read("3D/3dmodel.model"))
                ns = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
                self.assertEqual(root.attrib["unit"], "millimeter")
                self.assertEqual(len(root.find("m:build", ns)), 1)


if __name__ == "__main__":
    unittest.main()
