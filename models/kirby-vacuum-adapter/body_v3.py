"""Existing-hole prototype: 5 mm OUTSIDE diameter, 3 mm bore, mm units.

The smooth 8 mm spigot has no oversize barb or thread. The shoulder stays
outside the toy. Fit, retention and the restricted flow require a physical
trial; this is not a load-bearing mount for the vacuum's weight.
"""
from dataclasses import dataclass
from adapter import Dimensions, nozzle_outer, nozzle_stop, capsule, capsule_wire, circle_wire, cylinder, loft


@dataclass(frozen=True)
class BodyV3:
    rear_outer: float = 5.0
    rear_bore: float = 3.0
    insertion: float = 8.0
    shoulder_diameter: float = 14.0
    transition_z: float = 43.0
    seat_z: float = 45.0
    tip_chamfer_length: float = .4
    tip_outer: float = 4.4

    @property
    def total_height(self):
        return self.seat_z + self.insertion


def body_v3(d=None):
    d=d or BodyV3()
    if not (0 < d.rear_bore < d.tip_outer <= d.rear_outer <= 5):
        raise ValueError('The existing-hole insert must stay within 5 mm OD with a hollow tip.')
    if not (0 < d.tip_chamfer_length < d.insertion and 23 < d.transition_z < d.seat_z):
        raise ValueError('Insertion, chamfer and transition lengths must be positive and ordered.')
    fit=Dimensions()
    w,h=36.4,12.4
    outside=nozzle_outer(fit,.30).union(nozzle_stop(fit))
    outside=outside.union(loft(capsule_wire(w,h,20),circle_wire(d.shoulder_diameter,d.transition_z)))
    outside=outside.union(cylinder(d.shoulder_diameter,d.seat_z-d.transition_z,d.transition_z))
    outside=outside.union(cylinder(d.rear_outer,d.insertion-d.tip_chamfer_length,d.seat_z))
    outside=outside.union(loft(circle_wire(d.rear_outer,d.total_height-d.tip_chamfer_length),
                               circle_wire(d.tip_outer,d.total_height)))
    inside=capsule(w-2*fit.nozzle_wall,h-2*fit.nozzle_wall,21,-1)
    inside=inside.union(loft(capsule_wire(w-2*fit.nozzle_wall,h-2*fit.nozzle_wall,20),
                              circle_wire(d.rear_bore,d.transition_z)))
    inside=inside.union(cylinder(d.rear_bore,d.total_height-d.transition_z+1,d.transition_z))
    return outside.cut(inside).clean()
