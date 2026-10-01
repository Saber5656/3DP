"""524 v7: preserve the approved statue/color stack and improve the bail.

Coordinates match v6: X left/right, -Y front, Z upright. Printing rotates the
rear onto the bed. Dimensions are mm. Physical quality is still unverified.
"""
import importlib.util
import json
from functools import lru_cache
from pathlib import Path
import sys

import manifold3d as m
import numpy as np

ROOT = Path(__file__).resolve().parent
V6 = ROOT.parent / "statue-v6"
sys.path.insert(0, str(V6))
spec = importlib.util.spec_from_file_location("keychain_previous", V6 / "build.py")
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
as_mesh = previous.as_mesh
orient_for_print = previous.orient_for_print
write_3mf = previous.write_3mf
COLORS = dict(yellow="#F9DF54", white="#FFFFFF", orange="#FF6A13", teal="#0050B3")
# The completed v6 print established these depths and its yellow backing as
# the appearance reference. Translucent blue intentionally mixes with yellow.
# Waste reduction must preserve this recipe unless a better result is proven.
SKINS = dict(white=1.0, orange=.8, teal=.85)


def loop_contours():
    """Return outer/inner [upright offset, print-height offset] contours.

    The flat underside has 1.6 mm of material below the round part of the bore.
    Its first layer can sit on a broad support interface, rather than the small
    tangent of a circular tube. The bore becomes a 45-degree roof above its
    round lower portion; the 2.4 mm horizontal gauge still passes through.
    """
    radius, floor, bore = 3.8, -3.2, 1.6
    start = np.arcsin(floor/radius)
    angles = np.linspace(start, np.pi-start, 145)
    outer = radius*np.column_stack([np.cos(angles), np.sin(angles)])
    angles = np.linspace(3*np.pi/4, 9*np.pi/4, 109)
    inner = bore*np.column_stack([np.cos(angles), np.sin(angles)])
    inner = np.vstack([inner, [0, bore*np.sqrt(2)]])
    return outer, inner


@lru_cache(maxsize=1)
def build_model():
    old = previous.build_model()
    character, outlines, profile = old['character'], old['outlines'], old['profile']

    def cap(polygons, depth):
        def warp(vertices):
            x, z, t = np.asarray(vertices).T
            y = -profile(x,z)[0] + depth - t*(depth+1.)
            return np.column_stack([x,y,z])
        return m.CrossSection(polygons).extrude(1).refine_to_length(.15).warp_batch(warp)

    white_cut = cap(outlines['eyes'], SKINS['white'])
    orange_cut = cap(outlines['digits'], SKINS['orange'])
    blue_cut = cap(outlines['mouth'], SKINS['teal'])
    outer, inner = loop_contours()
    section = m.CrossSection([outer]) - m.CrossSection([inner])
    # [u, v, extrusion] -> [X, Y, Z] = [extrusion-1.2, -v, u+40.8].
    eyelet = section.extrude(2.4).transform([[0,0,1,-1.2], [0,-1,0,0], [1,0,0,40.8]])
    connector = (m.Manifold.sphere(1.2,48).translate([0,0,34.2]) +
                 m.Manifold.sphere(1.2,48).translate([0,0,37.8])).hull()
    mount = eyelet + connector
    full = character + mount
    parts = dict(yellow=full-white_cut-blue_cut,
                 white=(white_cut-orange_cut)^character,
                 orange=(orange_cut^white_cut)^character,
                 teal=blue_cut^character)
    return dict(parts=parts, character=character, full=full, eyelet=eyelet,
                eyelet_center=(0,0,40.8), rear_mm=character.bounding_box()[4],
                root_overlap_mm3=(mount^character).volume(),
                connector_eyelet_overlap_mm3=(connector^eyelet).volume(),
                color_depth_mm=SKINS, colors=COLORS)


def support_blockers_for_print():
    """Keep the bore clear, without blocking the flat underside's supports."""
    rear = build_model()['rear_mm']
    return {'keep self supporting bore clear': m.Manifold.cube([6,4.6,6])
            .translate([-3,40.8-2.3,rear-1.4])}


def coupon_for_print():
    """Crop a connected rear/head strip at the SAME bed height as the full print.

    The rear strip retains bed contact; do not independently drop the cropped
    loop to the bed, since that would hide the actual supported-underside risk.
    """
    printed = orient_for_print(build_model()['parts'])['yellow']
    return printed ^ m.Manifold.cube([9,30,15.2]).translate([-4.5,16,0])


def main():
    out = ROOT / 'output'
    (out/'stl').mkdir(parents=True,exist_ok=True)
    model = build_model()
    parts = orient_for_print(model['parts'])
    for name, solid in parts.items():
        as_mesh(solid).export(out/'stl'/f'{name}.stl')
    write_3mf(out/'524-v7-color-source.3mf', parts, COLORS,
              support_blockers=support_blockers_for_print())
    coupon = coupon_for_print()
    as_mesh(coupon).export(out/'hook-quality-coupon.stl')
    write_3mf(out/'hook-quality-coupon.3mf', {'yellow':coupon}, COLORS,
              support_blockers=support_blockers_for_print())
    report = dict(body_preserved_from='statue-v6 / original Wood statue',
                  body_mm=as_mesh(model['character']).extents.tolist(),
                  overall_mm=as_mesh(model['full']).extents.tolist(),
                  eyelet_center=list(model['eyelet_center']), hole_axis='X',
                  eyelet_width_mm=2.4, outer_diameter_mm=7.6,
                  circular_gauge_mm=2.4, bore_radius_mm=1.6,
                  flat_underside_mm=2*np.sqrt(3.8**2-3.2**2), roof_angle_degrees=45,
                  color_depth_mm=SKINS, physical_validation='NOT_RUN',
                  parts={name:dict(volume_mm3=s.volume(),
                                  watertight=as_mesh(s).is_watertight)
                         for name,s in parts.items()})
    (out/'geometry.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
