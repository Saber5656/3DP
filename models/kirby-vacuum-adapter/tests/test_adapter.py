import unittest
import math
from dataclasses import replace
import cadquery as cq
from adapter import Dimensions, fit_coupon, adapter_body, rear_gasket

class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.d = Dimensions()

    def test_confirmed_measurements_and_unit_guard(self):
        self.assertEqual((self.d.nozzle_width,self.d.nozzle_height,self.d.nozzle_depth,self.d.kirby_depth),(37,13,20,8))
        with self.assertRaises(ValueError):
            replace(self.d,nozzle_height=1.3,nozzle_width=3.7).validate()

    def test_three_fit_sizes_match_measured_envelope(self):
        for clearance in (0.15,0.30,0.45):
            part=fit_coupon(self.d,clearance)
            section=part.section(10).val().BoundingBox()
            self.assertAlmostEqual(section.xlen,37-2*clearance,places=4)
            self.assertAlmostEqual(section.ylen,13-2*clearance,places=4)
            self.assertAlmostEqual(part.val().BoundingBox().zlen,23,places=4)
            self.assertTrue(part.val().isValid())
            self.assertEqual(len(part.solids().vals()),1)
            self.assertFalse(part.val().isInside(cq.Vector(0,0,10),1e-6))

    def test_adapter_is_one_hollow_solid(self):
        part=adapter_body(self.d)
        self.assertTrue(part.val().isValid())
        self.assertEqual(len(part.solids().vals()),1)
        self.assertAlmostEqual(part.val().BoundingBox().zlen,58,places=4)
        for z in [0.2,10,19.5,21,30,42.9,46,49.8,54,57.8]:
            self.assertFalse(part.val().isInside(cq.Vector(0,0,z),1e-6),f'Flow blocked at z={z}')
        # Both mating ends retain a material wall outside their flow openings.
        self.assertTrue(part.val().isInside(cq.Vector(0,5.5,10),1e-6))
        self.assertTrue(part.val().isInside(cq.Vector(10.7,0,57),1e-6))

    def test_adapter_preserves_successful_coupon_stop_envelope(self):
        # An oblique vacuum rim contacts the collar at different positions if
        # the adapter's collar is narrower than the physically tested coupon.
        coupon=fit_coupon(self.d,self.d.clearance_per_side)
        body=adapter_body(self.d)
        for z in (20.1,21.9,22.9):
            expected=coupon.section(z).val().BoundingBox()
            actual=body.section(z).val().BoundingBox()
            self.assertAlmostEqual(actual.xlen,expected.xlen,places=4)
            self.assertAlmostEqual(actual.ylen,expected.ylen,places=4)

    def test_rear_insertion_length_and_flow_size(self):
        part=adapter_body(self.d)
        for z in (50.01,54,57.99):
            b=part.section(z).val().BoundingBox()
            self.assertAlmostEqual(b.xlen,24-(z-50)/4,places=3)
        # 20 mm passage through the round end; the existing 5 mm hole is not retained.
        self.assertFalse(part.val().isInside(cq.Vector(9.8,0,54),1e-6))
        self.assertTrue(part.val().isInside(cq.Vector(10.6,0,54),1e-6))

    def test_gasket_is_annular_and_single_body(self):
        part=rear_gasket(self.d)
        self.assertTrue(part.val().isValid())
        self.assertEqual(len(part.solids().vals()),1)
        self.assertAlmostEqual(part.val().BoundingBox().zlen,2)
        self.assertFalse(part.val().isInside(cq.Vector(0,0,1),1e-6))
        self.assertTrue(part.val().isInside(cq.Vector(15,0,1),1e-6))

if __name__=='__main__': unittest.main()
