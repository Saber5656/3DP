"""Acceptance checks for the 40 mm, four-material keychain."""
import unittest
import tempfile
from pathlib import Path
import zipfile
from xml.etree import ElementTree as ET
import trimesh
import numpy as np
import manifold3d as m
from shapely.geometry import Polygon, Point
from build import build_model, as_mesh, write_3mf, fit_coupon


class KeychainGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = build_model()

    def test_character_has_requested_height_and_real_rounded_depth(self):
        mesh = as_mesh(self.model['character'])
        self.assertAlmostEqual(mesh.extents[2], 40, places=3)
        self.assertAlmostEqual(mesh.extents[0], 150*40/153, places=4)
        self.assertAlmostEqual(mesh.extents[1], 85*40/153, places=4)
        reference = trimesh.load_mesh(Path(__file__).parents[1]/"source/wood-reference/body-review-only.stl")
        reference.apply_translation([0, 0, -15])
        reference.apply_scale(40/153)
        self.assertAlmostEqual(mesh.volume, reference.volume, delta=.01)
        from scipy.spatial import cKDTree
        self.assertLess(cKDTree(reference.vertices).query(mesh.vertices)[0].max(), 1e-6)
        self.assertLess(cKDTree(mesh.vertices).query(reference.vertices)[0].max(), 1e-6)
        # Front and back at the centre differ from the surface near the outline.
        center = self.model['profile'](0, 21)
        edge = self.model['profile'](-19, 21)
        self.assertGreater(center[1], edge[1] + 1)

    def test_loop_is_above_the_front_back_and_left_right_centre(self):
        from math import atan2, degrees, hypot
        x,y,z = self.model['eyelet_center']
        self.assertAlmostEqual(x, 0, places=6)
        self.assertAlmostEqual(y, 0, places=6)
        cm = as_mesh(self.model['full']).center_mass
        self.assertGreater(z, 39)
        self.assertLess(degrees(atan2(hypot(x-cm[0], y-cm[1]), z-cm[2])), 2)

    def test_four_material_volumes_are_closed_and_disjoint(self):
        parts = self.model['parts']
        self.assertEqual(set(parts), {'yellow', 'white', 'orange', 'teal'})
        for name, solid in parts.items():
            mesh = as_mesh(solid)
            self.assertTrue(mesh.is_watertight, name)
            self.assertTrue(mesh.is_winding_consistent, name)
            self.assertGreater(mesh.volume, 0, name)
            self.assertGreater(mesh.area_faces.min(), 0, name)
        for i, (name, a) in enumerate(parts.items()):
            for other, b in list(parts.items())[i + 1:]:
                self.assertLess((a ^ b).volume(), 0.001, (name, other))

    def test_material_partition_preserves_original_full_volume(self):
        volume = sum(s.volume() for s in self.model['parts'].values())
        self.assertAlmostEqual(volume, self.model['full'].volume(), places=3)
        self.assertEqual(len(as_mesh(self.model['full']).split()), 1)
        self.assertEqual(len(as_mesh(self.model['parts']['orange']).split()), 3)
        self.assertEqual(len(as_mesh(self.model['parts']['yellow']).split()), 1)

    def test_eyelet_is_open_and_rooted_in_the_character(self):
        full = self.model['full']
        self.assertGreater(self.model['eyelet_root_overlap_mm3'], 10)
        # A real cylinder checks the whole opening, not just sampled centre points.
        gx, gy, gz = self.model["eyelet_gauge_center"]
        gauge = m.Manifold.cylinder(4.2, 1.2, circular_segments=96).rotate([0, 90, 0]).translate([gx-2.1, gy, gz])
        self.assertLess((full ^ gauge).volume(), .0001)
        self.assertGreaterEqual(self.model['eyelet_tube_diameter_mm'], 1.8)
        self.assertLessEqual(self.model['eyelet_outer_diameter_mm'], 7)
        self.assertLess(self.model['eyelet_exposed_volume_mm3'], 50)
        self.assertEqual(self.model['eyelet_hole_axis'], 'X')

    def test_top_loop_preserves_body_and_stays_compact(self):
        full = as_mesh(self.model['full'])
        self.assertGreater(full.extents[2], 40)
        self.assertLessEqual(full.extents[2], 44.3)
        np.testing.assert_allclose(full.bounds[:, :2], as_mesh(self.model['character']).bounds[:, :2], atol=1e-6)

    def test_ring_plane_is_perpendicular_to_face_and_mount_is_connected(self):
        dims = as_mesh(self.model['eyelet']).extents
        np.testing.assert_allclose(dims, [1.8,6.8,6.8], atol=1e-5)
        self.assertGreater(self.model['eyelet_connector_overlap_mm3'], 3)

    def test_sideways_hole_blocker_covers_roof_with_each_print_origin(self):
        from build import orient_for_print, support_blockers_for_print
        for original in (self.model['full'], fit_coupon()):
            blocker = next(iter(support_blockers_for_print(original).values()))
            printed = orient_for_print({'full':original})['full']
            # A support blocker must reach the upper ring surfaces to exclude
            # supports generated there; it does not subtract printed geometry.
            self.assertGreater((blocker ^ printed).volume(), 1)
            gx,gy,gz = self.model['eyelet_gauge_center']
            rear = original.bounding_box()[4]
            cz = rear-gy
            printed_ring = self.model['eyelet'].rotate([-90,0,0]).translate([0,0,rear])
            bottom = printed_ring ^ m.Manifold.cube([20,20,10]).translate([gx-10,gz-10,cz-12])
            roof = printed_ring ^ m.Manifold.cube([6,2.8,4]).translate([gx-3,gz-1.4,cz+.9])
            self.assertGreater(bottom.volume(), 1)
            self.assertLess((bottom ^ blocker).volume(), .0001)
            self.assertGreater(roof.volume(), 1)
            self.assertLess((roof-blocker).volume(), .0001)
            probe = m.Manifold.cylinder(4.2,1.0,circular_segments=96).rotate([0,90,0]).translate([gx-2.1,gz,rear-gy])
            self.assertLess((probe-blocker).volume(), .0001)

    def test_face_keeps_handwritten_digits_and_dark_teal_mouth(self):
        self.assertEqual(len(self.model['outlines']['digits']), 3)
        self.assertEqual(len(self.model['outlines']['mouth']), 1)
        self.assertNotEqual(self.model['colors']['teal'].lower(), '#000000')
        self.assertEqual(self.model['background_included'], False)

    def test_exported_stl_and_3mf_retain_closed_geometry_and_colors(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, solid in self.model['parts'].items():
                mesh = as_mesh(solid)
                path = root / (name + '.stl')
                mesh.export(path)
                readback = trimesh.load_mesh(path)
                self.assertTrue(readback.is_watertight, name)
                self.assertTrue(readback.is_winding_consistent, name)
                np.testing.assert_allclose(readback.bounds, mesh.bounds, atol=1e-5)
            path = root / 'assembly.3mf'
            write_3mf(path, self.model['parts'], self.model['colors'])
            scene = trimesh.load(path, force='scene')
            self.assertEqual(len(scene.geometry), 4)
            np.testing.assert_allclose(scene.bounds, as_mesh(self.model['full']).bounds, atol=1e-5)
            with zipfile.ZipFile(path) as archive:
                xml = ET.fromstring(archive.read('Metadata/model_settings.config'))
                values = [part.find("metadata[@key='extruder']").get('value')
                          for part in xml.findall('object/part')]
                self.assertEqual(values, ['1', '2', '3', '4'])

    def test_fit_coupon_preserves_actual_rear_ring_and_opening(self):
        mesh = as_mesh(fit_coupon())
        self.assertEqual(len(mesh.split()), 1)
        self.assertLess(mesh.volume, as_mesh(self.model['full']).volume/10)
        gx, gy, gz = self.model["eyelet_gauge_center"]
        gauge = m.Manifold.cylinder(4.2, 1.2, circular_segments=96).rotate([0, 90, 0]).translate([gx-2.1, gy, gz])
        self.assertLess((fit_coupon() ^ gauge).volume(), .0001)
        self.assertLess((self.model['eyelet'] - fit_coupon()).volume(), .0001)

    def test_print_orientation_has_back_down_and_colors_up(self):
        from build import orient_for_print
        parts = orient_for_print(self.model['parts'])
        zmin = min(s.bounding_box()[2] for s in parts.values())
        zmax = max(s.bounding_box()[5] for s in parts.values())
        self.assertAlmostEqual(zmin, 0, places=6)
        for name in ('white','orange','teal'):
            self.assertGreater(parts[name].bounding_box()[2], zmax*.65)
        for name in parts:
            self.assertAlmostEqual(parts[name].volume(), self.model['parts'][name].volume(), places=4)

    def test_bambu_support_blocker_is_not_a_printed_material(self):
        from build import orient_for_print, support_blockers_for_print
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'controlled.3mf'
            write_3mf(path, orient_for_print(self.model['parts']), self.model['colors'],
                      support_blockers=support_blockers_for_print())
            with zipfile.ZipFile(path) as archive:
                config = ET.fromstring(archive.read('Metadata/model_settings.config'))
                parts = config.findall('object/part')
                self.assertEqual(len([p for p in parts if p.get('subtype')=='normal_part']), 4)
                blockers = [p for p in parts if p.get('subtype')=='support_blocker']
                self.assertEqual(len(blockers), 1)
                self.assertIsNone(blockers[0].find("metadata[@key='extruder']"))

    def test_optional_source_dots_are_attached_and_preserve_body_size(self):
        model = build_model(include_dots=True)
        mesh = as_mesh(model['full'])
        self.assertEqual(model['dots'], 'two original dots with added yellow stems')
        self.assertEqual(len(mesh.split()), 1)
        self.assertEqual(len(as_mesh(model['parts']['yellow']).split()), 1)
        self.assertAlmostEqual(as_mesh(model['character']).extents[2], 40, places=3)
        self.assertLess(mesh.bounds[0, 2], -3)
        for outline in model['outlines']['dots']:
            x, z = np.mean(outline, axis=0)
            self.assertTrue(mesh.contains([[x, 0, z]])[0])
        self.assertAlmostEqual(sum(s.volume() for s in model['parts'].values()),
                               model['full'].volume(), places=3)


if __name__ == '__main__':
    unittest.main()
