"""Parametric CAD for a fit-first Kirby rear vacuum adapter. Dimensions are mm.

The measured envelope is confirmed; a capsule profile and the rear geometry
are provisional. The 20 mm nozzle stem deliberately has no guessed oblique
cut. Its contact with the real oblique inlet must be checked with a coupon.
"""
from dataclasses import dataclass
import cadquery as cq

@dataclass(frozen=True)
class Dimensions:
    nozzle_width: float = 37.0
    nozzle_height: float = 13.0
    nozzle_depth: float = 20.0
    kirby_depth: float = 8.0
    clearance_per_side: float = 0.30
    nozzle_wall: float = 1.60
    rear_bore: float = 20.0
    rear_outer_base: float = 24.0
    rear_outer_tip: float = 22.0
    rear_flange: float = 36.0
    transition_end: float = 43.0
    rear_flange_top: float = 50.0
    gasket_thickness: float = 2.0

    def validate(self):
        if not (10 <= self.nozzle_width <= 100 and 5 <= self.nozzle_height <= self.nozzle_width):
            raise ValueError('Check nozzle dimensions and units: expected millimetres.')
        if not (0 <= self.clearance_per_side <= .6):
            raise ValueError('Unsupported clearance')
        if self.nozzle_height-2*self.clearance_per_side-2*self.nozzle_wall <= 2:
            raise ValueError('Nozzle bore too small')
        if self.rear_outer_tip-self.rear_bore < 2:
            raise ValueError('Rear tip wall must be at least 1 mm')
        if self.nozzle_depth >= self.transition_end:
            raise ValueError('Transition has no length')
        return self


def capsule_wire(width,height,z=0):
    return cq.Workplane('XY',origin=(0,0,z)).slot2D(width,height).val()


def circle_wire(diameter,z=0):
    return cq.Workplane('XY',origin=(0,0,z)).circle(diameter/2).val()


def capsule(width,height,length,z=0):
    return cq.Workplane('XY',origin=(0,0,z)).slot2D(width,height).extrude(length)


def cylinder(diameter,length,z=0):
    return cq.Workplane('XY',origin=(0,0,z)).circle(diameter/2).extrude(length)


def loft(a,b):
    return cq.Workplane('XY').newObject([cq.Solid.makeLoft([a,b],ruled=True)])


def nozzle_size(d,clearance):
    return d.nozzle_width-2*clearance,d.nozzle_height-2*clearance


def nozzle_outer(d,clearance):
    w,h=nozzle_size(d,clearance)
    return capsule(w,h,d.nozzle_depth).faces('<Z').edges().chamfer(.45)


def nozzle_stop(d):
    # Reuse the tested coupon's rim contact envelope in the full adapter.
    return capsule(d.nozzle_width+8,d.nozzle_height+8,3,d.nozzle_depth)


def fit_coupon(d=None,clearance=.30):
    d=(d or Dimensions()).validate()
    w,h=nozzle_size(d,clearance)
    stem=nozzle_outer(d,clearance)
    grip=nozzle_stop(d)
    solid=stem.union(grip)
    inner=capsule(w-2*d.nozzle_wall,h-2*d.nozzle_wall,d.nozzle_depth+5,-1)
    solid=solid.cut(inner)
    # Small shallow outer witness marks show insertion at 5, 10, 15 mm.
    # They remove 0.15 mm only, are not leaks and do not protrude into the fit.
    for z in (5,10,15):
        notch=cq.Workplane('XY').box(8,.30,.30).translate((0,h/2,z))
        solid=solid.cut(notch)
    return solid.clean()


def adapter_body(d=None):
    d=(d or Dimensions()).validate()
    w,h=nozzle_size(d,d.clearance_per_side)
    iw,ih=w-2*d.nozzle_wall,h-2*d.nozzle_wall
    outside=nozzle_outer(d,d.clearance_per_side)
    transition=loft(capsule_wire(w,h,d.nozzle_depth),circle_wire(d.rear_outer_base,d.transition_end))
    outside=outside.union(transition)
    # Preserve the successful coupon's collar; may need external support.
    outside=outside.union(nozzle_stop(d))
    # Gradual 45 degree underside to a wide rear support flange.
    slope_end=d.rear_flange_top-1
    ramp=loft(circle_wire(d.rear_outer_base,d.transition_end),circle_wire(d.rear_flange,slope_end))
    outside=outside.union(ramp).union(cylinder(d.rear_flange,1,slope_end))
    rear=loft(circle_wire(d.rear_outer_base,d.rear_flange_top),circle_wire(d.rear_outer_tip,d.rear_flange_top+d.kirby_depth))
    outside=outside.union(rear)
    inside=capsule(iw,ih,d.nozzle_depth+1,-1)
    inside=inside.union(loft(capsule_wire(iw,ih,d.nozzle_depth),circle_wire(d.rear_bore,d.transition_end)))
    inside=inside.union(cylinder(d.rear_bore,d.rear_flange_top+d.kirby_depth-d.transition_end+1,d.transition_end))
    return outside.cut(inside).clean()


def rear_gasket(d=None):
    d=(d or Dimensions()).validate()
    # Flat provisional washer; rear curvature and compression remain unmeasured.
    return cylinder(d.rear_flange,d.gasket_thickness).cut(cylinder(d.rear_outer_base+.4,d.gasket_thickness+2,-1)).clean()


def coupon_print_orientation(part):
    # Put the broad grip on the bed; the narrow stem points up, bore stays open.
    return part.rotate((0,0,0),(1,0,0),180).translate((0,0,23))
