"""Parametric, constructive-solid Ramiel display models. All geometry uses mm.

Run from this directory: ../../.venv/bin/python build.py
The star is a reference-based sculptural interpretation, not a canonical mesh.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET

import manifold3d as md
import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parent


def box(size, pos=(0, 0, 0)):
    return md.Manifold.cube(size).translate(pos)


def cylinder(radius, height, pos=(0, 0, 0)):
    return md.Manifold.cylinder(height, radius, circular_segments=64).translate(pos)


def to_mesh(solid):
    data = solid.to_mesh64()
    return trimesh.Trimesh(vertices=np.asarray(data.vert_properties)[:, :3],
                           faces=np.asarray(data.tri_verts), process=True)


def from_mesh(mesh):
    return md.Manifold(md.Mesh64(np.asarray(mesh.vertices, dtype=np.float64),
                                 np.asarray(mesh.faces, dtype=np.uint64)))


def pyramid(half_side, bottom_z, top_z):
    vertices = [[x, y, bottom_z] for x, y in
                [(-half_side, -half_side), (half_side, -half_side),
                 (half_side, half_side), (-half_side, half_side)]]
    vertices.append([0, 0, top_z])
    return md.Manifold.hull_points(vertices)


def bed_oriented(solid):
    bottom = solid.bounding_box()[2]
    return solid.translate([0, 0, -bottom])


def five_ring(radius, depth, angle):
    return np.array([[radius*math.cos(math.radians(angle+72*i)),
                      radius*math.sin(math.radians(angle+72*i)), depth] for i in range(5)])


def figure_envelope(cfg):
    """Five oblique quadrangular pyramids and compact, aligned rear relief."""
    scale = cfg["star_width"] / (2 * math.cos(math.pi / 10) * 79)
    tips = five_ring(79, cfg["star_front_depth"], -90) * scale
    inner_radius = cfg["star_inner_radius"]
    inner = five_ring(inner_radius, 18, -90) * scale
    valleys = five_ring(32, 0, -54) * scale
    back = five_ring(2 * 32 * math.cos(math.pi / 5) - inner_radius, -18, -90) * scale
    centre_back = np.array([0, 0, -12 * scale])
    envelope = md.Manifold.hull_points(np.vstack([inner, valleys, [centre_back]]))
    arm_bases = []
    for i in range(5):
        # Four coplanar corners form each rhombic root; the fifth point is its apex.
        root = np.array([inner[i], valleys[(i - 1) % 5], back[i], valleys[i]])
        arm_bases.append(root.tolist())
        # Connect each full root to the centre without filling a convex rear skirt.
        envelope += md.Manifold.hull_points(np.vstack([root, [centre_back]]))
        envelope += md.Manifold.hull_points(np.vstack([root, [tips[i]]]))
    rear_tips = five_ring(cfg["star_rear_radius"], cfg["star_rear_depth"], -90) * scale
    for i in range(5):
        radial = tips[i, :2] / np.linalg.norm(tips[i, :2])
        tangent = np.array([-radial[1], radial[0]])
        root = np.array([[*(radial * 10), -12], [*(radial * 22 + tangent * 12), -12],
                         [*(radial * 34), -12], [*(radial * 22 - tangent * 12), -12]]) * scale
        envelope += md.Manifold.hull_points(np.vstack([root, [rear_tips[i]]]))
    # The rim alternates between an arm's inner corner and the gap beside it.
    # Ten triangular sloping faces meet at the core, with five deep V-shaped
    # valleys extending between the arms. A convex cutter would lose this star.
    rim = np.array([point for pair in zip(inner, valleys) for point in pair])
    recess = md.Manifold()
    for i in range(10):
        floor = np.array([[0, 0, 0], rim[i], rim[(i + 1) % 10]])
        top = floor.copy()
        top[:, 2] = 100 * scale
        recess += md.Manifold.hull_points(np.vstack([floor, top]))
    envelope -= recess
    return envelope, {"front_tips": tips.tolist(), "rear_tips": rear_tips.tolist(),
                      "arm_bases": arm_bases, "inner_ridges": inner.tolist(),
                      "throat_floor": [0, 0, 0], "mouth_rim": rim.tolist()}


def city_base(envelope_world, tips_world, cfg):
    """A city with roofs carved from the body's lower envelope, open from above."""
    cy, radius = -14., cfg["city_base_diameter"] / 2
    foundation = cylinder(radius, 4, (0, cy, 0))
    blocks, records = md.Manifold(), []
    for i, x in enumerate([-46, -30, -14, 2, 18, 34, 50]):
        for j, y in enumerate([-62, -46, -30, -14, 2, 18, 34]):
            width, depth = 10 + (i + j) % 3 * 2, 10 + (2 * i + j) % 3 * 2
            if math.hypot(abs(x) + width / 2, abs(y - cy) + depth / 2) > radius - 2:
                continue
            height = 8 + ((i * 11 + j * 7) % 6) * 4
            blocks += box([width, depth, height], (x - width / 2, y - depth / 2, 4))
            records.append([x, y, width, depth, height, "building"])
    for x in [-17, 17]:
        for y in [-32, -10, 12]:
            blocks += box([28, 18, 48], (x - 14, y - 9, 4))
            records.append([x, y, 28, 18, 48, "conforming_roof"])
    # Courtyards around all tips keep the fragile apices free of supporting posts.
    # 7.5 mm avoids a zero-width tangency at the x=7 mm building boundary.
    for x, y, _ in tips_world:
        blocks -= cylinder(7.5, 160, (x, y, 4))
    removal = envelope_world.minkowski_sum(md.Manifold.sphere(cfg["city_clearance"], circular_segments=12))
    removal = removal.minkowski_sum(box([.01, .01, 200], (-.005, -.005, 0)))
    city = (foundation + (blocks - removal)).simplify(1e-4)
    # CSG can leave micrometre-scale edges where sloping roofs meet. Collapse
    # duplicate vertices at 1e-5 mm precision, then validate the closed surface.
    mesh = to_mesh(city)
    mesh.merge_vertices(digits_vertex=5)
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.remove_unreferenced_vertices()
    if not mesh.is_watertight or not mesh.is_winding_consistent:
        raise ValueError("City mesh cleanup did not preserve a closed solid")
    cleaned = from_mesh(mesh)
    if abs(cleaned.volume() - city.volume()) > .01:
        raise ValueError("City mesh cleanup changed the geometry beyond tolerance")
    return cleaned, records


def analyze_city_support(body_world, base, tips_world):
    """Finite 2 mm XY sampling of nearly touching, opposing lower/roof surfaces.

    This measures potential bearing regions, not load capacity or physical fit.
    """
    from scipy.spatial import ConvexHull
    points = []
    step = 2.
    for x in np.arange(-60., 61., step):
        for y in np.arange(-74., 47., step):
            start, end = [x, y, .1], [x, y, 190.]
            body_hits, base_hits = body_world.ray_cast(start, end), base.ray_cast(start, end)
            if not body_hits or not base_hits:
                continue
            bottom = min(body_hits, key=lambda hit: hit.position[2])
            roof = max(base_hits, key=lambda hit: hit.position[2])
            gap = bottom.position[2] - roof.position[2]
            bn, rn = np.array(bottom.normal), np.array(roof.normal)
            if 0 <= gap < .8 and bn[2] < -.35 and rn[2] > .35 and np.dot(-bn, rn) > .9:
                points.append([x, y, bottom.position[2], gap, *bn])
    if len(points) < 3:
        raise ValueError("City has insufficient conforming support surfaces")
    p = np.asarray(points)
    hull = ConvexHull(p[:, :2])
    boundary = p[hull.vertices, :2]
    com = to_mesh(body_world).center_mass
    edges = np.roll(boundary, -1, axis=0) - boundary
    delta = com[:2] - boundary
    margins = (edges[:, 0] * delta[:, 1] - edges[:, 1] * delta[:, 0]) / np.linalg.norm(edges, axis=1)
    tip_distances = np.linalg.norm(p[:, None, :3] - np.asarray(tips_world)[None, :, :], axis=2)
    # Flood-fill samples on the same sloping face, across adjacent grid cells.
    lookup = {tuple(q[:2]): i for i, q in enumerate(p)}
    unvisited = set(range(len(p)))
    patches = []
    while unvisited:
        stack, group = [unvisited.pop()], []
        while stack:
            index = stack.pop()
            group.append(index)
            for dx, dy in [(-step, 0), (step, 0), (0, -step), (0, step)]:
                neighbour = lookup.get((p[index, 0] + dx, p[index, 1] + dy))
                if neighbour in unvisited and np.dot(p[index, 4:], p[neighbour, 4:]) > .99:
                    unvisited.remove(neighbour)
                    stack.append(neighbour)
        q = p[group]
        patches.append({"samples": len(group), "projected_candidate_area_mm2": len(group) * step ** 2,
                        "xy_span_mm": np.ptp(q[:, :2], axis=0).tolist()})
    patches.sort(key=lambda patch: patch["samples"], reverse=True)
    return {"sample_spacing_mm": step, "samples": len(points),
            "projected_candidate_area_mm2": len(points) * step ** 2,
            "estimated_sloped_candidate_area_mm2": float((step ** 2 / np.abs(p[:, 6])).sum()),
            "shell_com_support_hull_margin_mm": float(margins.min()), "uniform_shell_com_mm": com.tolist(),
            "contact_x_span_mm": float(np.ptp(p[:, 0])), "contact_y_span_mm": float(np.ptp(p[:, 1])),
            "tip_near_contact_count": int((tip_distances.min(axis=1) < 7.5).sum()),
            "nearest_tip_to_contact_mm": float(tip_distances.min()),
            "candidate_patches": patches, "tip_exclusion_radius_mm": 7.5,
            "points_xy_z_gap_normal": p.tolist(),
            "limitations": "Potential bearing region with clearance; finite samples, uniform-density shell COM. No physical load, friction or tolerance validation."}


def build_models(cfg):
    parts = {}
    h = cfg["default_height"] / 2
    a = h / math.sqrt(2)
    wall = cfg["default_wall"]
    outer = pyramid(a, 0, h)
    slope = a / h
    inner_a = a - wall * math.sqrt(1 + slope*slope)
    inner_tip = inner_a / slope
    # A closed octahedral shell: one outer surface and one enclosed cavity.
    outer += pyramid(a, 0, -h)
    inner = pyramid(inner_a, 0, inner_tip) + pyramid(inner_a, 0, -inner_tip)
    parts["default_body"] = outer - inner
    cup = cylinder(30, 4) + cylinder(13, 18, (0, 0, 4))
    cup_cavity = pyramid((25-11.8)*slope, 25, 11.8)
    parts["default_cradle"] = cup - cup_cavity
    parts["default_tip_test"] = pyramid(12*slope, 12, 0)

    envelope, landmarks = figure_envelope(cfg)
    kernel = md.Manifold.sphere(1, circular_segments=12)
    km = to_mesh(kernel)
    inradius = np.abs(np.sum(km.triangles_center * km.face_normals, axis=1)).min()
    kernel = kernel.scale([cfg["star_wall"] / inradius] * 3)
    body = envelope - envelope.minkowski_difference(kernel)
    core_r = cfg["star_core_diameter"] / 2
    seat_z = cfg["star_bead_center_z"]
    bowl = md.Manifold.sphere(core_r+1.3,circular_segments=48).translate([0,0,seat_z])
    bowl = bowl.trim_by_plane([0,0,-1],-seat_z)
    seat = md.Manifold.sphere(core_r+.15,circular_segments=64).translate([0,0,seat_z])
    seat += cylinder(core_r+.15,50,(0,0,seat_z))
    body = (body+bowl)-seat
    parts["star_body"] = body
    parts["red_core"] = md.Manifold.sphere(core_r,circular_segments=64)
    tilt = cfg["star_display_tilt"]
    rot = trimesh.transformations.rotation_matrix(math.radians(90 - tilt), [1, 0, 0])
    center_h = 10 - to_mesh(envelope.rotate([90 - tilt, 0, 0])).bounds[0, 2]
    def display(solid):
        return solid.rotate([90 - tilt, 0, 0]).translate([0, 0, center_h])
    tips_world = trimesh.transform_points(np.asarray(landmarks["front_tips"]), rot) + [0, 0, center_h]
    base, city_buildings = city_base(display(envelope), tips_world, cfg)
    city_support = analyze_city_support(display(body), base, tips_world)
    parts["star_base"] = base
    parts["star_ray_test"] = body ^ box([50,33,60],(-25,-90,-10))
    parts["bead_seat_coupon"] = (bowl-seat) + box([10,10,1.2],(-5,-5,seat_z-core_r-1.6))

    for thickness in (.8, 1.2, 1.6):
        parts[f"blue_tile_{thickness:.1f}mm"] = box([20, 20, thickness])
    print_parts = {name: bed_oriented(solid) for name, solid in parts.items()
                   if name != "red_core"}
    # Edge-down avoids a broad horizontal ceiling in the enclosed cavity.
    edge_up = np.array([.5, .5, 1 / math.sqrt(2)])
    edge_rotation = trimesh.geometry.align_vectors(edge_up, [0, 0, 1])
    print_parts["default_body"] = bed_oriented(parts["default_body"].transform(edge_rotation[:3, :]))
    print_parts["default_tip_test"] = bed_oriented(parts["default_tip_test"].rotate([180, 0, 0]))

    default_center = 62.0
    default_assembly = [
        ("default_body", parts["default_body"].translate([0, 0, default_center])),
        ("default_cradle", parts["default_cradle"]),
    ]
    star_assembly = [("star_body", display(body)),
                     ("red_core", display(parts["red_core"].translate([0,0,seat_z]))),
                     ("star_base",base)]
    # Upright print pose; validate the exported v6 paths independently of prior versions.
    star_rotation = trimesh.geometry.align_vectors(cfg["star_print_up"], [0,0,1])
    for name in ("star_body", "star_ray_test"):
        print_parts[name] = bed_oriented(parts[name].transform(star_rotation[:3,:]))
    return {"parts": parts, "print_parts": print_parts,
            "assemblies": {"default": default_assembly, "star": star_assembly},
            "joints": {"star_city": {"clearance": cfg["city_clearance"]}},
            "star_center_height": center_h, "star_display_tilt": tilt,
            "star_landmarks": landmarks, "star_tip_positions_world": tips_world.tolist(),
            "city_buildings": city_buildings, "city_support": city_support}


def part_color(name):
    if "core" in name:
        return [215, 24, 48, 255]
    if any(x in name for x in ("cradle", "mast", "base")):
        return [55, 61, 72, 255]
    return [18, 95, 196, 255]


def export_3mf(pieces, target):
    """Core-spec geometry-only assembly, explicitly mm; no machine/G-code preset."""
    ns = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
    ET.register_namespace("", ns)
    tag = lambda name: f"{{{ns}}}{name}"
    root = ET.Element(tag("model"), {"unit": "millimeter", "xml:lang": "en-US"})
    ET.SubElement(root, tag("metadata"), {"name": "Title"}).text = "Ramiel display assembly - not a print plate"
    resources = ET.SubElement(root, tag("resources"))
    build = ET.SubElement(root, tag("build"))
    material = ET.SubElement(resources, tag("basematerials"), {"id": "1"})
    for name, rgb in [("blue", [18, 95, 196]), ("red", [215, 24, 48]), ("stand", [55, 61, 72])]:
        ET.SubElement(material, tag("base"), {"name": name, "displaycolor": "#"+"".join(f"{c:02X}" for c in rgb)+"FF"})
    for index, (name, solid) in enumerate(pieces, 2):
        mesh = to_mesh(solid)
        color_id = "1" if "core" in name else ("2" if any(x in name for x in ("cradle", "mast", "base")) else "0")
        obj = ET.SubElement(resources, tag("object"), {"id": str(index), "type": "model", "name": name, "pid": "1", "pindex": color_id})
        elem = ET.SubElement(obj, tag("mesh"))
        verts = ET.SubElement(elem, tag("vertices"))
        for v in mesh.vertices:
            ET.SubElement(verts, tag("vertex"), dict(zip(("x", "y", "z"), (f"{x:.8f}" for x in v))))
        tris = ET.SubElement(elem, tag("triangles"))
        for f in mesh.faces:
            ET.SubElement(tris, tag("triangle"), dict(zip(("v1", "v2", "v3"), map(str, f))))
    # Group the whole display as components of one build object, preserving pose
    # in slicers that otherwise place each independent build item onto the bed.
    assembly_id = str(len(pieces) + 2)
    assembly = ET.SubElement(resources, tag("object"), {"id": assembly_id, "type": "model", "name": "Display assembly"})
    components = ET.SubElement(assembly, tag("components"))
    for index in range(2, len(pieces) + 2):
        ET.SubElement(components, tag("component"), {"objectid": str(index)})
    ET.SubElement(build, tag("item"), {"objectid": assembly_id})
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("3D/3dmodel.model", ET.tostring(root, encoding="utf-8", xml_declaration=True))
        archive.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
        archive.writestr("_rels/.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')


def main():
    cfg = json.loads((ROOT / "design.json").read_text())
    model = build_models(cfg)
    out = ROOT / "output"
    (out / "stl").mkdir(parents=True, exist_ok=True)
    records = []
    for name, solid in model["print_parts"].items():
        mesh = to_mesh(solid)
        path = out / "stl" / f"{name}.stl"
        mesh.export(path)
        reloaded = trimesh.load_mesh(path)
        assert np.allclose(mesh.bounds, reloaded.bounds, atol=1e-4), name
        assert reloaded.is_watertight and reloaded.is_winding_consistent, name
        records.append({"part": name, "file": path.relative_to(ROOT).as_posix(),
                        "dimensions_mm": reloaded.extents.tolist(), "volume_mm3": float(reloaded.volume),
                        "watertight": bool(reloaded.is_watertight), "winding_consistent": bool(reloaded.is_winding_consistent),
                        "components": len(reloaded.split()), "triangles": len(reloaded.faces),
                        "min_triangle_area_mm2": float(reloaded.area_faces.min()),
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    for assembly_name, pieces in model["assemblies"].items():
        scene = trimesh.Scene()
        for name, solid in pieces:
            mesh = to_mesh(solid)
            mesh.visual.face_colors = part_color(name)
            scene.add_geometry(mesh, node_name=name, geom_name=name)
        # glTF uses metres and Y-up. Convert this preview, while STLs and 3MF stay mm.
        scene.apply_transform(trimesh.transformations.rotation_matrix(-math.pi/2, [1, 0, 0]))
        scene.apply_scale(.001)
        (out / f"{assembly_name}-preview.glb").write_bytes(scene.export(file_type="glb"))
        export_3mf(pieces, out / f"{assembly_name}-display-assembly.3mf")
    versions = {p: importlib.metadata.version(p) for p in
                ("numpy", "trimesh", "manifold3d", "scipy", "matplotlib", "pillow", "rtree")}
    report = {"revision": cfg["revision"], "units": "mm", "versions": versions, "parts": records,
              "joints": model["joints"], "star_center_height_mm": model["star_center_height"],
              "limitations": ["Geometry report only; see printing/ and JOB-RECORD.md for slicing and physical status. The enclosed void has a separate inward-facing surface, not a floating part.",
                              "Star tips are mathematically pointed; tiny terminal geometry can disappear in slicing.",
                              "Star arm proportions, aligned rear relief and display angle are design estimates from photos, not official measurements.",
                              "Displayed red core is a full 3 mm sphere representing an aftermarket bead. It is not included in the print plates. No LED.",
                              "Pairwise triangle self-intersection and slicer-specific thin-wall checks require separate validation."]}
    (out / "city-support.json").write_text(json.dumps(model["city_support"], indent=2)+"\n")
    (out / "mesh-report.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps({"parts": len(records), "output": "output/", "versions": versions}))


if __name__ == "__main__":
    main()
