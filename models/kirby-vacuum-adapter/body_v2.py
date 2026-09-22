"""First complete rear bulkhead prototype, custom coarse threads, millimetres.

Only the vacuum fitting has been physically tried. The nut is installed from
inside the opened mouth. Rear wall thickness is 8 mm by user report; the thread
allows adjustment. This is a matched printed pair, not a standard M28 thread.
"""
from dataclasses import dataclass
import cadquery as cq
from adapter import Dimensions, nozzle_outer, nozzle_stop, capsule, capsule_wire, circle_wire, cylinder, loft


@dataclass(frozen=True)
class BodyV2:
    bore: float = 20.0
    root_diameter: float = 25.6
    major_diameter: float = 28.0
    pitch: float = 4.0
    thread_length: float = 22.0
    radial_clearance: float = .30
    axial_clearance: float = .15
    transition_z: float = 43.0
    flange_diameter: float = 40.0
    flange_z: float = 53.0
    nut_diameter: float = 36.0
    nut_height: float = 8.0
    rear_wall_reported: float = 8.0

    @property
    def total_height(self):
        return self.flange_z+self.thread_length


def thread_blank(d, height, female=False, z=0):
    """Twist a closed radial profile: root, sloping flank, and flat crest.

    Unlike unioning an open helical sweep to a core, this remains one closed
    solid before boolean operations. Four boundary edges keep the root and
    crest circular and avoid hundreds of narrow helical surface patches.
    The female profile adds radial and angular flank clearance.
    """
    import math
    gap = d.radial_clearance if female else 0.
    angular_gap = 2*math.pi*d.axial_clearance/d.pitch if female else 0.
    base_angle=3*math.pi/4+angular_gap
    crest_angle=math.pi/8+angular_gap
    root=d.root_diameter/2+gap; crest=d.major_diameter/2+gap
    def polar(r,a): return (r*math.cos(a),r*math.sin(a))
    left=[polar(root+(crest-root)*i/12,-base_angle+(base_angle-crest_angle)*i/12)
          for i in range(1,13)]
    right=[polar(crest-(crest-root)*i/12,crest_angle+(base_angle-crest_angle)*i/12)
           for i in range(1,13)]
    profile=cq.Workplane('XY',origin=(0,0,z)).moveTo(*polar(root,-base_angle))
    profile=profile.spline(left,includeCurrent=True).threePointArc(polar(crest,0),polar(crest,crest_angle))
    profile=profile.spline(right,includeCurrent=True).threePointArc(polar(root,math.pi),polar(root,-base_angle)).close()
    return profile.twistExtrude(height,360*height/d.pitch)


def threaded_stem(d):
    stem = thread_blank(d,d.thread_length)
    # Last 1.2 mm is a tapered lead, without reducing the cylindrical root.
    limit = cylinder(d.major_diameter+.02,d.thread_length-1.2)
    limit = limit.union(loft(circle_wire(d.major_diameter+.02,d.thread_length-1.2),
                            circle_wire(d.root_diameter,d.thread_length)))
    return stem.intersect(limit).clean()


def body_v2(d=None):
    d = d or BodyV2()
    fit = Dimensions()
    w,h = 36.4,12.4
    iw,ih = w-2*fit.nozzle_wall,h-2*fit.nozzle_wall
    outside = nozzle_outer(fit,.30).union(nozzle_stop(fit))
    outside = outside.union(loft(capsule_wire(w,h,20),circle_wire(d.root_diameter,d.transition_z)))
    outside = outside.union(loft(circle_wire(d.root_diameter,d.transition_z),
                                circle_wire(d.flange_diameter,d.flange_z-2)))
    outside = outside.union(cylinder(d.flange_diameter,2,d.flange_z-2))
    outside = outside.union(threaded_stem(d).translate((0,0,d.flange_z)))
    inside = capsule(iw,ih,21,-1)
    inside = inside.union(loft(capsule_wire(iw,ih,20),circle_wire(d.bore,d.transition_z)))
    inside = inside.union(cylinder(d.bore,d.total_height-d.transition_z+1,d.transition_z))
    return outside.cut(inside).clean()


def retaining_nut(d=None):
    d = d or BodyV2()
    nut = cylinder(d.nut_diameter,d.nut_height)
    # Shallow external grip scallops, accessible by fingers through the mouth.
    import math
    for i in range(12):
        a=2*math.pi*i/12
        cutter = cylinder(2.4,d.nut_height+2,-1).translate((
            d.nut_diameter/2*math.cos(a),d.nut_diameter/2*math.sin(a),0))
        nut = nut.cut(cutter)
    cutter = thread_blank(d,d.nut_height+2*d.pitch,True,-d.pitch)
    nut = nut.cut(cutter)
    # Symmetric entry reliefs for starting the paired thread from either end.
    for z,da,db in [(0,d.major_diameter+.8,d.root_diameter+2*d.radial_clearance),
                     (d.nut_height-.7,d.root_diameter+2*d.radial_clearance,d.major_diameter+.8)]:
        nut = nut.cut(loft(circle_wire(da,z),circle_wire(db,z+.7)))
    return nut.clean()


def assembled_nut(nut,d,stack):
    return nut.rotate((0,0,0),(0,0,1),360*stack/d.pitch).translate((0,0,d.flange_z+stack))
