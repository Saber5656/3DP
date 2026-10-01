"""Image-contour CAD for a rounded 40 mm mascot. Dimensions are millimetres."""
import json
from functools import lru_cache
from pathlib import Path
from xml.etree import ElementTree as ET
import zipfile

import manifold3d as m
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
import trimesh

ROOT = Path(__file__).resolve().parent
COLORS = {'yellow': '#F9DF54', 'white': '#F7F5F2',
          'orange': '#E98249', 'teal': '#376978'}


def as_mesh(solid):
    mesh = solid.to_mesh64()
    result = trimesh.Trimesh(np.round(np.asarray(mesh.vert_properties)[:, :3], 7),
                            np.asarray(mesh.tri_verts), process=False)
    # Boolean interfaces can contain coincident zero-area/duplicate triangles.
    # Canonicalize to 1e-7 mm precision; never fill intentional openings.
    result.merge_vertices(digits_vertex=7)
    result.update_faces(result.nondegenerate_faces(height=1e-12))
    result.update_faces(result.unique_faces())
    result.remove_unreferenced_vertices()
    if not result.is_watertight or not result.is_winding_consistent:
        raise ValueError('Mesh validation failed after interface cleanup')
    if abs(result.volume - solid.volume()) > 0.002:
        raise ValueError('Interface cleanup changed the geometry volume')
    return result


@lru_cache(maxsize=2)
def build_model(include_dots=False):
    traced = json.loads((ROOT / 'source/traced-contours.json').read_text())
    raw = {'body': [], 'eyes': [], 'digits': [], 'mouth': [], 'dots': []}
    keys = {'body': 'body', 'white': 'eyes', 'digit': 'digits', 'mouth': 'mouth', 'dot': 'dots'}
    for part in traced['parts']:
        for polygon in part['polygons']:
            if polygon['holes']:
                raise ValueError('Unexpected contour holes: update the CAD conversion')
            raw[keys[part['kind']]].append([[x, -y] for x, y in polygon['exterior']])
    body_points = np.vstack(raw['body'])
    lo, hi = body_points.min(axis=0), body_points.max(axis=0)
    factor = 40 / (hi[1] - lo[1])
    offset = [(lo[0] + hi[0]) / 2, lo[1]]
    outlines = {k: [(np.asarray(poly) - offset) * factor for poly in polygons]
                for k, polygons in raw.items()}
    step, margin = 0.08, 4
    x0, z0 = -26., -margin
    shape = (int(48 / step) + 1, int(52 / step) + 1)
    masks = {}
    for name, polygons in outlines.items():
        raster = Image.new('L', (shape[1], shape[0]))
        draw = ImageDraw.Draw(raster)
        for poly in polygons:
            draw.polygon([((x - x0) / step, (z - z0) / step) for x, z in poly], fill=255)
        masks[name] = np.asarray(raster) > 0
    signed = (ndimage.distance_transform_edt(masks['body']) -
              ndimage.distance_transform_edt(~masks['body'])) * step
    distance = np.maximum(0, ndimage.gaussian_filter(signed, .3 / step))
    profile = np.sqrt(1 - np.exp(-distance / 2.9))
    profile = ndimage.gaussian_filter(profile, .25 / step)
    profile /= profile.max()
    white_distance = ndimage.distance_transform_edt(masks['eyes']) * step
    t = np.clip(white_distance / .8, 0, 1)
    dome = ndimage.gaussian_filter(t * t * (3 - 2 * t), .12 / step)
    front = .48 + 6.15 * profile + .42 * dome
    back = .48 + 7.0 * profile

    def sample(field, x, z):
        x, z = np.broadcast_arrays(np.asarray(x), np.asarray(z))
        values = ndimage.map_coordinates(field, [(z.ravel() - z0) / step,
                                                 (x.ravel() - x0) / step], order=1)
        return values.reshape(x.shape)

    def both(x, z):
        return sample(front, x, z), sample(back, x, z)

    section = m.CrossSection(outlines['body'])
    # Refine both caps before warping so the back is a curved volume, not a slab.
    def inflate(vertices):
        x, z, t = np.asarray(vertices).T
        return np.column_stack([x, (1 - t) * sample(back, x, z) - t * sample(front, x, z), z])
    character = section.extrude(1).refine_to_length(.3).warp_batch(inflate)

    def color_cap(polygons, thickness):
        def warp(vertices):
            x, z, t = np.asarray(vertices).T
            # Extend past the exterior before intersecting. Independently
            # triangulated coincident curved caps would leave tiny slivers.
            y = -sample(front, x, z) + thickness - t * (thickness + 1.0)
            return np.column_stack([x, y, z])
        solid = m.CrossSection(polygons).extrude(1).refine_to_length(.25).warp_batch(warp)
        return solid

    white_cut = color_cap(outlines['eyes'], 1.0)
    digit_cut = color_cap(outlines['digits'], .8)
    mouth_cut = color_cap(outlines['mouth'], .85)
    orange = (digit_cut ^ white_cut) ^ character
    white = (white_cut - digit_cut) ^ character
    teal = mouth_cut ^ character

    # A round torus partly embedded in the upper rear of the head. Its exposed
    # arc is a small bail; the front silhouette has no protruding tag or stem.
    center = (1.1, 7.6, 32.1)
    major_radius, tube_radius = 2.5, .9
    eyelet = (m.CrossSection.circle(tube_radius, 32).translate([major_radius, 0])
              .revolve(96).rotate([0, 90, 0]).translate(center))
    overlap = (eyelet ^ character).volume()
    full = character + eyelet
    if include_dots:
        # Detached marks need added material to become a single physical object.
        # Preserve their traced front outlines; stems are an explicit design option.
        dots = m.CrossSection(outlines['dots']).extrude(2.4).rotate([90, 0, 0]).translate([0, 1.2, 0])
        centers = [np.mean(poly, axis=0) for poly in outlines['dots']]
        roots = [np.array([6., 4.]), *centers]
        stems = []
        for a, b in zip(roots, roots[1:]):
            cap = (m.CrossSection.circle(.8, 48).translate(a) +
                   m.CrossSection.circle(.8, 48).translate(b)).hull()
            stems.append(cap.extrude(1.8).rotate([90, 0, 0]).translate([0, 1.5, 0]))
        full = m.Manifold.batch_boolean([full, dots, *stems], m.OpType.Add)
    yellow = full - white_cut - mouth_cut
    parts = {'yellow': yellow, 'white': white, 'orange': orange, 'teal': teal}
    return dict(parts=parts, character=character, full=full, outlines=outlines,
                profile=both, colors=COLORS, background_included=False,
                eyelet=eyelet, eyelet_center=center,
                eyelet_gauge_center=(1.1, 7.95, 32.1), eyelet_gauge_diameter_mm=2.4,
                eyelet_tube_diameter_mm=2*tube_radius,
                eyelet_outer_diameter_mm=2*(major_radius+tube_radius),
                eyelet_nominal_inner_diameter_mm=2*(major_radius-tube_radius),
                eyelet_root_overlap_mm3=overlap,
                eyelet_exposed_volume_mm3=(eyelet-character).volume(),
                body_height_mm=40., dots=('two original dots with added yellow stems' if include_dots
                                        else 'body only; detached source dots omitted'))


def write_3mf(path, parts, colors, support_blockers=None):
    """Core 3MF assembly with explicit Bambu volume-to-filament metadata."""
    ns = 'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'
    ET.register_namespace('', ns)
    def tag(name): return '{' + ns + '}' + name
    root = ET.Element(tag('model'), {'unit': 'millimeter'})
    ET.SubElement(root, tag('metadata'), {'name': 'Title'}).text = '524 keychain / 40 mm'
    resources = ET.SubElement(root, tag('resources'))
    palette = ET.SubElement(resources, tag('basematerials'), {'id': '1'})
    settings = ET.Element('config')
    assembled = ET.SubElement(settings, 'object', {'id': '100'})
    ET.SubElement(assembled, 'metadata', {'key': 'name', 'value': '524 keychain 40mm'})
    ET.SubElement(assembled, 'metadata', {'key': 'extruder', 'value': '1'})
    for i, (name, solid) in enumerate(parts.items()):
        ET.SubElement(palette, tag('base'), {'name': name, 'displaycolor': colors[name] + 'FF'})
        obj = ET.SubElement(resources, tag('object'), {'id': str(10 + i), 'type': 'model',
                            'name': name, 'pid': '1', 'pindex': str(i)})
        mesh = as_mesh(solid)
        data = ET.SubElement(obj, tag('mesh'))
        vertices = ET.SubElement(data, tag('vertices'))
        triangles = ET.SubElement(data, tag('triangles'))
        for x, y, z in mesh.vertices:
            ET.SubElement(vertices, tag('vertex'), {'x': f'{x:.7f}', 'y': f'{y:.7f}', 'z': f'{z:.7f}'})
        for a, b, c in mesh.faces:
            ET.SubElement(triangles, tag('triangle'), {'v1': str(a), 'v2': str(b), 'v3': str(c)})
        part = ET.SubElement(assembled, 'part', {'id': str(10 + i), 'subtype': 'normal_part'})
        ET.SubElement(part, 'metadata', {'key': 'name', 'value': name})
        ET.SubElement(part, 'metadata', {'key': 'extruder', 'value': str(i + 1)})
    blocker_ids = []
    for i, (name, solid) in enumerate((support_blockers or {}).items()):
        object_id = str(90+i)
        blocker_ids.append(object_id)
        obj = ET.SubElement(resources, tag('object'), {'id': object_id, 'type': 'model', 'name': name})
        mesh = as_mesh(solid)
        data = ET.SubElement(obj, tag('mesh'))
        vertices = ET.SubElement(data, tag('vertices'))
        triangles = ET.SubElement(data, tag('triangles'))
        for x, y, z in mesh.vertices:
            ET.SubElement(vertices, tag('vertex'), {'x': f'{x:.7f}', 'y': f'{y:.7f}', 'z': f'{z:.7f}'})
        for a, b, c in mesh.faces:
            ET.SubElement(triangles, tag('triangle'), {'v1': str(a), 'v2': str(b), 'v3': str(c)})
        part = ET.SubElement(assembled, 'part', {'id': object_id, 'subtype': 'support_blocker'})
        ET.SubElement(part, 'metadata', {'key': 'name', 'value': name})
    assembly = ET.SubElement(resources, tag('object'), {'id': '100', 'type': 'model', 'name': '524 keychain'})
    components = ET.SubElement(assembly, tag('components'))
    for i in range(len(parts)):
        ET.SubElement(components, tag('component'), {'objectid': str(10 + i)})
    for object_id in blocker_ids:
        ET.SubElement(components, tag('component'), {'objectid': object_id})
    plate = ET.SubElement(settings, 'plate')
    for key, value in [('plater_id', '1'), ('locked', 'false'), ('filament_map_mode', 'Manual'),
                       ('filament_maps', ' '.join('1' for _ in parts)),
                       ('filament_volume_maps', ' '.join('0' for _ in parts))]:
        ET.SubElement(plate, 'metadata', {'key': key, 'value': value})
    instance = ET.SubElement(plate, 'model_instance')
    for key, value in [('object_id', '100'), ('instance_id', '0'), ('identify_id', '100')]:
        ET.SubElement(instance, 'metadata', {'key': key, 'value': value})
    build = ET.SubElement(root, tag('build'))
    ET.SubElement(build, tag('item'), {'objectid': '100'})
    types = '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/><Default Extension="config" ContentType="application/xml"/></Types>'
    rels = '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>'
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', types)
        archive.writestr('_rels/.rels', rels)
        archive.writestr('3D/3dmodel.model', ET.tostring(root, encoding='utf-8', xml_declaration=True))
        archive.writestr('Metadata/model_settings.config', ET.tostring(settings, encoding='utf-8', xml_declaration=True))


def fit_coupon():
    """Actual rear loop and adjacent head surface, cropped for a small trial."""
    region = m.Manifold.cube([10, 11, 11]).translate([-3.9, 1, 27])
    return build_model()['full'] ^ region


def orient_for_print(parts):
    """Keep all colors aligned: rear down, face up, lowest point at bed Z=0."""
    rotated = {name: solid.rotate([-90, 0, 0]) for name, solid in parts.items()}
    zmin = min(s.bounding_box()[2] for s in rotated.values())
    return {name: s.translate([0, 0, -zmin]) for name, s in rotated.items()}


def support_blockers_for_print():
    """Nonprinting Bambu modifier: keep removable supports out of the tiny bore."""
    gx, gy, gz = build_model()['eyelet_gauge_center']
    return {'keep rear loop clear': m.Manifold.cube([6, 4.6, 6.5]).translate([gx-3, gz-2.3, 0])}


def main():
    result = build_model()
    out = ROOT / 'output'
    (out / 'stl').mkdir(parents=True, exist_ok=True)
    report = {}
    print_parts = orient_for_print(result['parts'])
    for name, solid in print_parts.items():
        mesh = as_mesh(solid)
        mesh.export(out / 'stl' / (name + '.stl'))
        report[name] = dict(volume_mm3=float(mesh.volume), watertight=bool(mesh.is_watertight),
                            winding_consistent=bool(mesh.is_winding_consistent),
                            components=len(mesh.split()), triangles=len(mesh.faces))
    print_full = orient_for_print({'full': result['full']})['full']
    print_coupon = orient_for_print({'coupon': fit_coupon()})['coupon']
    as_mesh(print_full).export(out / '524-keychain-solid.stl')
    as_mesh(print_coupon).export(out / 'hook-fit-coupon.stl')
    write_3mf(out / '524-keychain-40mm-color.3mf', print_parts, COLORS)
    write_3mf(out / '524-keychain-40mm-bambu-face-up-v2.3mf', print_parts, COLORS,
              support_blockers=support_blockers_for_print())
    write_3mf(out / 'hook-fit-coupon.3mf', {'yellow': print_coupon}, COLORS,
              support_blockers=support_blockers_for_print())
    all_mesh = as_mesh(result['full'])
    scene = trimesh.Scene()
    for name, solid in result['parts'].items():
        mesh = as_mesh(solid)
        mesh.visual.face_colors = trimesh.visual.color.hex_to_rgba(COLORS[name])
        scene.add_geometry(mesh, geom_name=name, node_name=name)
    scene.export(out / '524-keychain-40mm.glb')
    summary = dict(revision='rear-loop-v2', body_height_mm=40,
                   body_dimensions_xyz_mm=as_mesh(result['character']).extents.tolist(),
                   overall_dimensions_xyz_mm=all_mesh.extents.tolist(),
                   eyelet_outer_diameter_mm=result['eyelet_outer_diameter_mm'],
                   eyelet_nominal_inner_diameter_mm=result['eyelet_nominal_inner_diameter_mm'],
                   eyelet_verified_clearance_diameter_mm=result['eyelet_gauge_diameter_mm'],
                   eyelet_tube_diameter_mm=result['eyelet_tube_diameter_mm'],
                   eyelet_exposed_volume_mm3=result['eyelet_exposed_volume_mm3'],
                   eyelet_root_overlap_mm3=result['eyelet_root_overlap_mm3'], parts=report,
                   exported_orientation='rear down / face up / bed Z=0',
                   print_dimensions_xyz_mm=as_mesh(print_full).extents.tolist(),
                   color_match='image approximation; physical swatch test required',
                   hardware_fit='NOT_RUN', physical_print='NOT_RUN', dots=result['dots'])
    (out / 'geometry-report.json').write_text(json.dumps(summary, indent=2) + '\n')
    with_dots = build_model(include_dots=True)
    write_3mf(out / '524-keychain-40mm-with-dots.3mf', orient_for_print(with_dots['parts']), COLORS)
    write_3mf(out / '524-keychain-with-dots-bambu-face-up-v2.3mf', orient_for_print(with_dots['parts']), COLORS,
              support_blockers=support_blockers_for_print())
    dots_mesh = as_mesh(with_dots['full'])
    as_mesh(orient_for_print({'full': with_dots['full']})['full']).export(out / '524-keychain-with-dots-solid.stl')
    (out / 'with-dots-report.json').write_text(json.dumps(dict(
        body_height_mm=40, overall_dimensions_xyz_mm=dots_mesh.extents.tolist(),
        components=len(dots_mesh.split()), watertight=bool(dots_mesh.is_watertight),
        stem_width_mm=1.6, stem_depth_mm=1.8, physical_print='NOT_RUN',
        note=with_dots['dots']), indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
