import unittest
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import models


class ModelAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.designs = models.build_all()

    def test_selection_is_five_unique_designs(self):
        self.assertEqual(set(self.designs), {'D1', 'D2', 'D3', 'D4', 'B4'})

    def test_logo_has_seven_openings(self):
        logo = models.logo_polygon(50)
        self.assertEqual(logo.geom_type, 'Polygon')
        self.assertEqual(len(logo.interiors), 7)
        self.assertFalse(logo.contains(models.Point(0, 0)))

    def test_solids_and_size(self):
        for name, design in self.designs.items():
            self.assertTrue(design.parts, name)
            bounds = np.vstack([models.mesh(p.solid).bounds for p in design.parts])
            extent = np.ptp(bounds, axis=0)
            self.assertLessEqual(extent[0], 100, name)
            self.assertAlmostEqual(extent[2],48,places=3,msg=name)
            self.assertGreater(extent[2], 40, name)
            for part in design.parts:
                m = models.mesh(part.solid)
                with self.subTest(model=name, part=part.name):
                    self.assertTrue(m.is_watertight)
                    self.assertTrue(m.is_winding_consistent)
                    self.assertTrue(m.is_volume)
                    self.assertEqual(m.body_count, 1)
                    self.assertGreater(m.volume, 2)

    def test_print_orientation_and_materials(self):
        colors = set()
        for d in self.designs.values():
            for p in d.parts:
                colors.add(p.color)
                m = models.mesh(models.print_solid(p))
                self.assertAlmostEqual(m.bounds[0, 2], 0, places=5)
                self.assertLess(m.extents.max(), 256)
        self.assertEqual(colors, {'white', 'black', 'orange', 'translucent_blue', 'gray'})

    def test_color_parts_do_not_interpenetrate(self):
        for name,d in self.designs.items():
            for i,a in enumerate(d.parts):
                for b in d.parts[i+1:]:
                    overlap=(a.solid ^ b.solid).volume()
                    self.assertLess(overlap, .05, (name,a.name,b.name,overlap))

    def test_pillow_can_slide_in_from_front(self):
        parts={p.name:p.solid for p in self.designs['D3'].parts}
        for distance in (.25,1,3,5,10,20,40):
            self.assertLess((parts['hugging_clawd'] ^ parts['pillow'].translate((0,-distance,0))).volume(),.01,distance)

    def test_binary_stl_roundtrip_stays_closed(self):
        import io,trimesh
        for key,d in self.designs.items():
            for p in d.parts:
                m=models.mesh(models.print_solid(p))
                loaded=trimesh.load_mesh(io.BytesIO(m.export(file_type='stl')),file_type='stl')
                self.assertTrue(loaded.is_watertight,(key,p.name))
                self.assertEqual(loaded.body_count,1,(key,p.name))

    def test_eyes_and_source_logo_detail_survive(self):
        for name in ['D3','D4','B4']:
            eyes=[p for p in self.designs[name].parts if 'eye' in p.name]
            self.assertEqual(len(eyes),2,name)
            self.assertTrue(all(min(models.mesh(p.solid).extents)>=1.4 for p in eyes))
        for name in ['D2','D3','D4']:
            logos=[p for p in self.designs[name].parts if p.name.endswith('logo')]
            self.assertEqual(len(logos),1)
            # Watertight genus-7 extruded knot: Euler = 2 - 2*7.
            self.assertEqual(models.mesh(logos[0].solid).euler_number,-12,name)


if __name__ == '__main__':
    unittest.main()
