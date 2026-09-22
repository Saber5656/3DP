import unittest
import math
import cadquery as cq
from adapter import Dimensions, fit_coupon
from body_v3 import BodyV3, body_v3


class BodyV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = BodyV3()
        cls.body = body_v3(cls.d)

    def test_actual_insert_is_five_mm_outer_not_inner(self):
        for dz in (.01, 1, 4, 7.5, 7.9):
            section = self.body.section(self.d.seat_z + dz)
            bounds = section.val().BoundingBox()
            self.assertLessEqual(bounds.xlen, 5.00001)
            self.assertLessEqual(bounds.ylen, 5.00001)
        section = self.body.section(self.d.seat_z + 4).val()
        self.assertAlmostEqual(section.BoundingBox().xlen, 5., places=4)
        for z in (46, 49, 52):
            self.assertFalse(self.body.val().isInside(cq.Vector(1.49, 0, z), 1e-6))
            self.assertTrue(self.body.val().isInside(cq.Vector(1.51, 0, z), 1e-6))

    def test_eight_mm_insert_and_continuous_airway(self):
        self.assertEqual(self.d.total_height - self.d.seat_z, 8.)
        self.assertTrue(self.body.val().isValid())
        self.assertEqual(len(self.body.solids().vals()), 1)
        for z in range(1, int(self.d.total_height)):
            for a in range(0, 360, 60):
                p = cq.Vector(1.4*math.cos(math.radians(a)),1.4*math.sin(math.radians(a)),z)
                self.assertFalse(self.body.val().isInside(p, 1e-6))
        # The shoulder stays outside the hole and prevents over-insertion.
        self.assertTrue(self.body.val().isInside(cq.Vector(6,0,self.d.seat_z-.1),1e-6))
        self.assertFalse(self.body.val().isInside(cq.Vector(3,0,self.d.seat_z+.1),1e-6))

    def test_tested_vacuum_fitting_is_preserved(self):
        coupon=fit_coupon(Dimensions(),.30)
        for z in (1,10,19.9,20.1,22.9):
            a=self.body.section(z).val().BoundingBox()
            b=coupon.section(z).val().BoundingBox()
            self.assertAlmostEqual(a.xlen,b.xlen,places=3)
            self.assertAlmostEqual(a.ylen,b.ylen,places=3)

    def test_invalid_oversize_tip_is_rejected(self):
        with self.assertRaises(ValueError):
            body_v3(BodyV3(tip_outer=6.))


if __name__ == '__main__':
    unittest.main()
