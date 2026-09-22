"""Independent acceptance checks on files after running scripts/build.py."""
import unittest
from pathlib import Path
import json
import numpy as np
import trimesh
import zipfile
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output'


@unittest.skipUnless((OUT/'validation.json').exists(), 'Run build.py first')
class ExportTests(unittest.TestCase):
    def test_materials_and_part_names_survive_exports(self):
        expected={'caffeine':{'C':'#32383FFF','N':'#367ED2FF','O':'#EE852CFF'},
                  'helicene_B':{'C':'#939DA9FF'},
                  'mof5_guest_CH4':{'guest_C':'#32383FFF','guest_H':'#F1F0E8FF'},
                  'mof5_assembly':{'lower':'#939DA9FF','upper':'#939DA9FF','guest':'#F1F0E8FF'}}
        ns={'m':'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'}
        for name,colors in expected.items():
            with self.subTest(name=name):
                with zipfile.ZipFile(OUT/(name+'.3mf')) as z:root=ET.fromstring(z.read('3D/3dmodel.model'))
                self.assertEqual(root.attrib['unit'],'millimeter')
                bases=root.findall('m:resources/m:basematerials/m:base',ns)
                objects=root.findall('m:resources/m:object',ns)
                actual={o.attrib['name']:bases[int(o.attrib['pindex'])].attrib['displaycolor'] for o in objects}
                self.assertEqual(actual,colors)
                self.assertEqual(len(root.findall('m:build/m:item',ns)),len(colors))
        for name,keys in [('caffeine',{'C','N','O'}),('helicene_B',{'C'}),
                          ('mof5_assembled',{'C','Zn','O','joint_collars','guest_C','guest_H'})]:
            scene=trimesh.load(OUT/(name+'.glb'))
            self.assertEqual(set(scene.geometry),keys)
            self.assertTrue(all(len(set(map(tuple,m.visual.vertex_colors)))==1 for m in scene.geometry.values()))
        # glTF uses metres, while the print exports use millimetres.
        for name,width in [('helicene_A',.100),('helicene_B',.100),('infinitene',.140),('caffeine',.110),('mof5_assembled',.150)]:
            self.assertAlmostEqual(trimesh.load(OUT/(name+'.glb')).extents.max(),width,delta=.00001)

    def test_every_print_part_is_a_single_closed_body(self):
        names=['helicene_A','helicene_B','infinitene','caffeine','mof5_lower','mof5_upper','mof5_guest_CH4','fit_coupon_3p3_3p4_3p5','fit_pin_3p0']
        for name in names:
            with self.subTest(name=name):
                m=trimesh.load_mesh(OUT/(name+'.stl'))
                self.assertTrue(m.is_watertight)
                self.assertTrue(m.is_winding_consistent)
                self.assertEqual(m.body_count,1)
                self.assertGreater(m.volume,0)
                self.assertTrue(np.isfinite(m.vertices).all())
                self.assertFalse((m.area_faces<1e-10).any())

    def test_3mf_roundtrip_and_design_size(self):
        for name,target in [('helicene_A',100),('helicene_B',100),('infinitene',140),('caffeine',110),('mof5_assembly',150)]:
            with self.subTest(name=name):
                scene=trimesh.load(OUT/(name+'.3mf'))
                self.assertAlmostEqual(scene.extents.max(),target,delta=.05)
                self.assertGreater(len(scene.geometry),0)

    def test_free_guest_has_no_intersection_with_closed_frame(self):
        lower=trimesh.load_mesh(OUT/'mof5_lower.stl')
        upper=trimesh.load_mesh(OUT/'mof5_upper.stl')
        guest=trimesh.load_mesh(OUT/'mof5_guest_CH4.stl')
        for a,b in [(lower,upper),(lower,guest),(upper,guest)]:
            collision=trimesh.boolean.intersection([a,b],engine='manifold')
            self.assertLess(abs(collision.volume),1e-3)

    def test_nine_sockets_use_selected_3p5_mm_fit(self):
        report=json.loads((OUT/'validation.json').read_text())['models']['mof5']
        lower=trimesh.load_mesh(OUT/'mof5_lower.stl')
        section=lower.section(plane_origin=[0,0,report['split_z_mm']-2],
                              plane_normal=[0,0,1])
        # Measure the exported bore contours, not just the declared parameter.
        bores=[np.ptp(path[:,:2],axis=0) for path in section.discrete
               if np.ptp(path[:,:2],axis=0).max()<4]
        self.assertEqual(len(bores),9)
        np.testing.assert_allclose(bores,3.5,atol=.001)
        self.assertEqual(report['socket_diameter_mm'],3.5)
        self.assertEqual(report['peg_diameter_mm'],3.0)

    def test_guest_carbon_core_survives_mesh_approximation(self):
        r=json.loads((OUT/'validation.json').read_text())['models']['mof5']['guest']
        # An icosphere's inscribed sphere is smaller than its circumscribed sphere.
        sphere=trimesh.creation.icosphere(subdivisions=3,radius=r['carbon_radius_mm'])
        inscribed=np.min(abs(np.einsum('ij,ij->i',sphere.face_normals,sphere.triangles_center)))
        # Allow 0.1 mm for the frame's mesh approximation/simplification.
        # This checks the original frame, not physical seams or FDM deformation.
        self.assertGreater(inscribed-r['aperture_radius_upper_bound_mm']-.1,.5)


if __name__=='__main__':unittest.main()
