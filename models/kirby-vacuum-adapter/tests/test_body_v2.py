import unittest
import cadquery as cq
import numpy as np
import trimesh
from shapely.geometry import Polygon
from adapter import Dimensions, fit_coupon
from body_v2 import BodyV2, body_v2, retaining_nut, assembled_nut


def mesh_of(part):
    vertices,faces=part.val().tessellate(.02,.12)
    return trimesh.Trimesh(vertices=[v.toTuple() for v in vertices],faces=faces,process=True)


def xy_section(mesh,z):
    section=mesh.section(plane_origin=(0,0,z),plane_normal=(0,0,1))
    loops=sorted([Polygon(p[:,:2]) for p in section.discrete],key=lambda p:p.area,reverse=True)
    result=loops[0]
    for loop in loops[1:]: result=result.difference(loop)
    return result


def move_nut(mesh,d,stack):
    m=mesh.copy()
    m.apply_transform(trimesh.transformations.rotation_matrix(2*np.pi*stack/d.pitch,(0,0,1)))
    m.apply_translation((0,0,d.flange_z+stack))
    return m


class BodyV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = BodyV2()
        cls.body = body_v2(cls.d)
        cls.nut = retaining_nut(cls.d)
        cls.body_mesh=mesh_of(cls.body)
        cls.nut_mesh=mesh_of(cls.nut)

    def test_body_preserves_tested_nozzle_and_stop(self):
        coupon = fit_coupon(Dimensions(), .30)
        for z in (1, 10, 19.9, 20.1, 22.9):
            a = self.body.section(z).val().BoundingBox()
            b = coupon.section(z).val().BoundingBox()
            self.assertAlmostEqual(a.xlen, b.xlen, places=3)
            self.assertAlmostEqual(a.ylen, b.ylen, places=3)

    def test_each_part_is_valid_and_flow_stays_open(self):
        for part in (self.body, self.nut):
            self.assertTrue(part.val().isValid())
            self.assertEqual(len(part.solids().vals()), 1)
        for z in range(1, int(self.d.total_height)):
            self.assertFalse(self.body.val().isInside(cq.Vector(0, 0, z), 1e-6))
        self.assertFalse(self.body.val().isInside(cq.Vector(9.9, 0, self.d.flange_z+10), 1e-6))
        for z in (55.,62.,73.):
            for a in range(0,360,45):
                self.assertTrue(self.body.val().isInside(cq.Vector(
                    11*np.cos(np.radians(a)),11*np.sin(np.radians(a)),z),1e-6))

    def test_threads_assemble_without_collision_for_wall_and_seal_stack(self):
        for stack in (8., 9., 10., 12.):
            nut=move_nut(self.nut_mesh,self.d,stack)
            for z in np.arange(.2,self.d.nut_height,.4)+self.d.flange_z+stack:
                overlap=xy_section(self.body_mesh,z).intersection(xy_section(nut,z)).area
                self.assertLess(overlap,.003,f'Collision at stack={stack}, z={z}')
            self.assertLess(stack+self.d.nut_height, self.d.thread_length)

    def test_thread_has_axial_retention_without_rotation(self):
        shifted=move_nut(self.nut_mesh,self.d,8.)
        shifted.apply_translation((0,0,self.d.pitch/2))
        z=self.d.flange_z+8+self.d.pitch/2+self.d.nut_height/2
        self.assertGreater(xy_section(self.body_mesh,z).intersection(xy_section(shifted,z)).area,1.)


if __name__ == '__main__':
    unittest.main()
