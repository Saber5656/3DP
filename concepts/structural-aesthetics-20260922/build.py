"""Parametric "ideal form" models for the ten structural-aesthetics concepts.

All geometry is in mm. Each builder returns a list of (part_name, Manifold,
color_key). Several concepts also return a second "motion" state so the render
can show what the object does. These are concept-stage solids for visual review;
clearances, hinge thickness and fits still need test pieces before printing.

Run from this directory: python build.py   (writes output/<id>/*.stl + mesh-report.json)
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import manifold3d as md
import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"

COLORS = {
    "purple": (150, 60, 170), "green": (150, 200, 60), "orange": (235, 120, 50),
    "white": (235, 235, 230), "black": (45, 45, 50), "blue": (70, 120, 220),
    "grey": (150, 155, 165), "teal": (60, 175, 170), "yellow": (240, 200, 60),
    "red": (215, 70, 70),
}


# ----------------------------------------------------------------- helpers
def box(sx, sy, sz, center=True):
    return md.Manifold.cube([sx, sy, sz], center)


def cyl(r, h, r_top=None, seg=96, center=False):
    return md.Manifold.cylinder(h, r, r if r_top is None else r_top, seg, center)


def sphere(r, seg=128):
    return md.Manifold.sphere(r, seg)


def torus(R, r, seg=96, rseg=32):
    profile = md.CrossSection.circle(r, rseg).translate([R, 0])
    return md.Manifold.revolve(profile, seg)


def rot_axis(solid, axis, deg):
    """Rotate about an arbitrary axis through the origin (Rodrigues)."""
    a = np.asarray(axis, float)
    a /= np.linalg.norm(a)
    t = math.radians(deg)
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    R = np.eye(3) + math.sin(t) * K + (1 - math.cos(t)) * K @ K
    m = np.zeros((3, 4))
    m[:, :3] = R
    return solid.transform(m)


def union(parts):
    parts = [p for p in parts if p is not None and not p.is_empty()]
    if not parts:
        return md.Manifold()
    return md.Manifold.batch_boolean(parts, md.OpType.Add)


def segment(p, q, r, seg=24):
    """Cylinder from p to q (used for strings / struts)."""
    p, q = np.asarray(p, float), np.asarray(q, float)
    d = q - p
    L = np.linalg.norm(d)
    c = cyl(r, L, seg=seg)
    z = np.array([0, 0, 1.0])
    d /= L
    axis = np.cross(z, d)
    if np.linalg.norm(axis) < 1e-9:
        c = c if d[2] > 0 else c.rotate([180, 0, 0])
    else:
        c = rot_axis(c, axis, math.degrees(math.acos(np.clip(z @ d, -1, 1))))
    return c.translate(p)


def to_mesh(solid):
    data = solid.to_mesh64()
    # process=False keeps Manifold's already-valid topology (vertex merging in
    # trimesh can break thin lattice struts).
    return trimesh.Trimesh(vertices=np.asarray(data.vert_properties)[:, :3],
                           faces=np.asarray(data.tri_verts), process=False)


# ------------------------------------------------------------ S1 spinner
def s1_segmented_spinner():
    R, T = 29.0, 3.2            # outer radius, shell thickness
    n = 8                       # meridian segments
    gap = 1.8                   # visible groove between segments
    cap_r, hole_r = 10.0, 8.0
    shell = sphere(R) - sphere(R - T)
    shell -= cyl(hole_r, 2 * R + 2, center=True)               # polar holes
    groove = (cyl(R + 1, gap, center=True) - cyl(R - 1.2, gap, center=True))
    shell -= groove                                               # equator groove
    cuts = [box(2 * R + 4, gap, 2 * R + 4).translate([R + 2, 0, 0]).rotate([0, 0, 360 / n * i])
            for i in range(n)]
    shell -= union(cuts)
    # hub: finger cap outside, bearing ring inside the polar hole
    zc = math.sqrt(R ** 2 - cap_r ** 2)
    cap = cyl(cap_r, 5.5).translate([0, 0, zc - 2.5])
    cap = cap + cyl(cap_r + 1.5, 1.6).translate([0, 0, zc + 3])
    bearing = cyl(hole_r - 0.3, 9, center=True).translate([0, 0, zc - 3.5]) - \
        cyl(3, 12, center=True).translate([0, 0, zc - 3.5])
    hub_top = cap + bearing
    hub_bot = hub_top.mirror([0, 0, 1])
    axle = cyl(2.6, 2 * zc + 4, center=True)
    # cross joints on the equator at every groove crossing
    joints = []
    for i in range(n):
        a = 360 / n * i
        cross = box(2.2, 8, 2.4) + box(2.2, 2.4, 8) + box(1.5, 3.2, 3.2)
        cross = cross.translate([R - 1.0, 0, 0]).rotate([0, 0, a])
        joints.append(cross)
    return [("shell", shell, "purple"), ("hub_top", hub_top, "green"),
            ("hub_bottom", hub_bot, "green"), ("axle", axle, "green"),
            ("joints", union(joints), "green")]


# ------------------------------------------------ S2 centrifugal opening ball
def s2_centrifugal_ball(open_deg=0.0):
    R, T = 27.0, 2.4
    n = 8
    hinge_z = -19.0             # petal root height (bottom hub top face)
    hinge_r = 9.5
    slit = 1.2
    shell = sphere(R) - sphere(R - T)
    shell = shell.trim_by_plane([0, 0, 1], hinge_z)                # remove below hub
    shell -= cyl(8.5, 12, center=True).translate([0, 0, R])        # top clearance
    cuts = [box(2 * R + 4, slit, 2 * R + 4).translate([R + 2, 0, 0]).rotate([0, 0, 360 / n * i + 180 / n])
            for i in range(n)]
    shell -= union(cuts)
    # weight bead at the petal tip so centrifugal force has something to pull
    tips = union([sphere(2.8, 48).translate([(R - 3.2) * math.cos(math.radians(a)),
                                              (R - 3.2) * math.sin(math.radians(a)), 16])
                  for a in [360 / n * i for i in range(n)]])
    shell = shell + tips
    petals = []
    wedge_angle = 360 / n
    for i in range(n):
        a0 = wedge_angle * i
        wedge = md.CrossSection([[[0, 0], [100 * math.cos(math.radians(a0 - wedge_angle / 2)),
                                           100 * math.sin(math.radians(a0 - wedge_angle / 2))],
                                  [100 * math.cos(math.radians(a0 + wedge_angle / 2)),
                                   100 * math.sin(math.radians(a0 + wedge_angle / 2))]]])
        petal = shell ^ md.Manifold.extrude(wedge, 200).translate([0, 0, -100])
        # flexure root: thin tab from hub to petal
        tab = box(hinge_r - 4, 4, 0.8).translate([hinge_r / 2 + 2 + (R - T) / 2 - hinge_r / 2, 0, hinge_z + 0.4]) \
            .rotate([0, 0, a0])
        petal = petal + tab
        if open_deg:
            hx, hy = hinge_r * math.cos(math.radians(a0)), hinge_r * math.sin(math.radians(a0))
            petal = petal.translate([-hx, -hy, -hinge_z]).rotate([0, 0, -a0]) \
                .rotate([0, open_deg, 0]).rotate([0, 0, a0]).translate([hx, hy, hinge_z])
        petals.append(petal)
    hub = cyl(hinge_r + 1.5, 6).translate([0, 0, hinge_z - 6])
    hub = hub + cyl(6, 4).translate([0, 0, hinge_z - 10])
    shaft = cyl(2.8, R + 8 - hinge_z).translate([0, 0, hinge_z - 4])
    top_cap = cyl(7, 5).translate([0, 0, R - 1]) + cyl(8.5, 1.5).translate([0, 0, R + 4])
    parts = [(f"petal_{i}", p, "purple" if i % 2 == 0 else "teal") for i, p in enumerate(petals)]
    parts += [("hub", hub, "green"), ("shaft", shaft, "green"), ("top_cap", top_cap, "green")]
    return parts


# ------------------------------------------------------------ S3 gimbal
def s3_gimbal():
    w, t = 4.5, 3.2            # ring width (radial), thickness (axial)
    radii = [36, 29.5, 23]
    normals = [[0, 1, 0], [1, 0, 0], [0, 0, 1]]
    colors = ["blue", "white", "blue"]
    parts = []
    for i, (r, nrm) in enumerate(zip(radii, normals)):
        ring = cyl(r, t, center=True) - cyl(r - w, t, center=True)
        if nrm == [0, 1, 0]:
            ring = ring.rotate([90, 0, 0])
        elif nrm == [1, 0, 0]:
            ring = ring.rotate([0, 90, 0])
        parts.append((f"ring_{i}", ring, colors[i]))
    # pins: outer->middle along z, middle->inner along y, inner->core along x
    pin_axes = [[0, 0, 1], [0, 1, 0], [1, 0, 0]]
    pins = []
    for i, ax in enumerate(pin_axes):
        r_out = radii[i] - w
        r_in = radii[i + 1] if i + 1 < len(radii) else 17
        pin = cyl(2.2, r_out - r_in + 2, seg=32).translate([0, 0, r_in - 1])
        if ax == [0, 0, 1]:
            p = pin + pin.mirror([0, 0, 1])
        elif ax == [0, 1, 0]:
            p = pin.rotate([-90, 0, 0]) + pin.rotate([90, 0, 0])
        else:
            p = pin.rotate([0, 90, 0]) + pin.rotate([0, -90, 0])
        pins.append(p)
    core = sphere(17, 96)
    core = core - cyl(2.9, 40, center=True).rotate([0, 90, 0]) + pins[2]
    core = core + cyl(6, 2).translate([0, 0, 15.5]) + cyl(6, 2).translate([0, 0, -17.5])
    foot = box(30, 14, 4).translate([0, 0, -radii[0] - 1.5]) + \
        (box(10, 8, 12).translate([0, 0, -radii[0] + 3]) - cyl(radii[0] - w + 0.4, 10, center=True).rotate([90, 0, 0]))
    parts += [("pins_outer", pins[0], "orange"), ("pins_middle", pins[1], "orange"),
              ("core", core, "orange"), ("foot", foot, "black")]
    return parts


# ------------------------------------------------------- S4 kaleidocycle
def s4_kaleidocycle(psi_a=0.9, a=20.0, d=28.0):
    """Six congruent disphenoid tetrahedra (hinge edges 2a, hinge distance d)
    joined in a ring. The ring is built with the S6 roto-reflection symmetry of
    a turning kaleidocycle: hinge k sits at azimuth 60k, alternating +z/-z, and
    tilts radially by psi (A hinges) / psi_b (B hinges). For a given A tilt the
    remaining radii, z offset and B tilt are solved so every hinge-to-hinge
    edge equals the tetrahedron's fixed edge length. psi_a ~0.9..1.2 rad are
    collision-free turning states for this d/a; the states near 0 and 1.5 rad
    would need slimmer tetrahedra (larger a/d) to pass through the middle."""
    from scipy.optimize import least_squares
    b = math.sqrt(2 * a * a + d * d)

    def hinge(k, r_a, r_b, z, p_a, p_b):
        ang = math.radians(60 * k)
        sgn = 1 if k % 2 == 0 else -1
        r, psi = (r_a, p_a) if k % 2 == 0 else (r_b, p_b)
        c = np.array([r * math.cos(ang), r * math.sin(ang), sgn * z])
        n = np.array([math.cos(ang), math.sin(ang), 0.0])
        u = math.cos(psi) * np.array([0, 0, 1.0]) - math.sin(psi) * n
        return c + a * u, c - a * u

    def edges(A, B):
        return [np.linalg.norm(A[i] - B[j]) for i in range(2) for j in range(2)]

    def resid(x, p_a):
        H = [hinge(k, x[0], x[1], x[2], p_a, x[3]) for k in range(3)]
        return np.array(edges(H[0], H[1]) + edges(H[1], H[2])) - b

    x = np.array([23.75, 22.0, 8.04, -1.01])          # known solution at psi_a = 0.9
    for p in np.linspace(0.9, psi_a, max(2, int(abs(psi_a - 0.9) / 0.1) + 2)):
        x = least_squares(resid, x, args=(p,)).x
    if np.abs(resid(x, psi_a)).max() > 1e-3:
        raise RuntimeError("kaleidocycle closure not satisfied")
    hinges = [hinge(k, x[0], x[1], x[2], psi_a, x[3]) for k in range(6)]
    parts = []
    palette = ["orange", "white", "teal", "orange", "white", "teal"]
    for k in range(6):
        pts = list(hinges[k]) + list(hinges[(k + 1) % 6])
        tet = md.Manifold.hull_points([list(map(float, p)) for p in pts])
        parts.append((f"tet_{k}", tet, palette[k]))
    return parts


# --------------------------------------------------------- S5 tensegrity
def s5_tensegrity():
    R = 46
    plate_t = 4
    gap_z0, gap_z1 = 33, 39          # the "floating" gap between the two arm tips
    bottom = cyl(R, plate_t)
    b_post = box(12, 12, 30 - plate_t + 0.1).translate([0, 0, plate_t + (30 - plate_t) / 2])
    b_arm = box(30, 12, 6).translate([13, 0, 30 - 3])
    b_hook = box(6, 12, 8).translate([25, 0, 30 + 1])            # rises to gap_z0
    bottom_part = bottom + b_post + b_arm + b_hook
    top_z = 72
    top = cyl(R, plate_t).translate([0, 0, top_z - plate_t])
    t_post = box(12, 12, top_z - plate_t - 42).translate([0, 0, (top_z - plate_t + 42) / 2])
    t_arm = box(30, 12, 6).translate([13, 0, 42 + 3])
    t_hook = box(6, 12, 8).translate([25, 0, 42 - 1])            # hangs down to gap_z1
    top_part = top + t_post + t_arm + t_hook
    strings = [segment([25, 0, gap_z0], [25, 0, gap_z1], 0.7)]
    for k in range(3):
        ang = math.radians(90 + 120 * k)
        x, y = (R - 4) * math.cos(ang), (R - 4) * math.sin(ang)
        strings.append(segment([x, y, plate_t], [x, y, top_z - plate_t], 0.7))
    eyelets = union([cyl(3, 2).translate([(R - 4) * math.cos(math.radians(90 + 120 * k)),
                                          (R - 4) * math.sin(math.radians(90 + 120 * k)), plate_t])
                     for k in range(3)] +
                    [cyl(3, 2).translate([(R - 4) * math.cos(math.radians(90 + 120 * k)),
                                          (R - 4) * math.sin(math.radians(90 + 120 * k)), top_z - plate_t - 2])
                     for k in range(3)])
    phone = box(64, 7, 120).rotate([-22, 0, 0]).translate([0, -8, 72 + 52])
    return [("bottom", bottom_part, "black"), ("top", top_part, "orange"),
            ("eyelets", eyelets, "black"), ("strings", union(strings), "grey"),
            ("phone_ghost", phone, "grey")]


# ------------------------------------------------------- S6 auxetic lattice
def s6_auxetic(stretch=0.0, cols=5, rows=6):
    """Re-entrant (bow-tie) honeycomb. stretch in [0,1] opens the cells."""
    W, h, s0, w, t = 14.0, 10.0, 4.0, 1.3, 2.4
    L = math.hypot(W / 2, s0)                    # inclined strut length is fixed
    s = s0 * (1 - 0.7 * stretch)
    Wh = math.sqrt(L * L - s * s)               # half width after rotation
    Wc = 2 * Wh
    struts = []

    def strut(p, q):
        p, q = np.array(p, float), np.array(q, float)
        d = q - p
        Lg = np.linalg.norm(d)
        ang = math.degrees(math.atan2(d[1], d[0]))
        b = box(Lg + w, w, t).rotate([0, 0, ang]).translate([*(p + q) / 2, t / 2])
        struts.append(b)

    for j in range(rows):
        for i in range(cols):
            x0 = i * Wc + (j % 2) * Wh
            y0 = j * (h - s)
            strut((x0, y0), (x0, y0 + h))
            strut((x0, y0), (x0 + Wh, y0 + s))
            strut((x0 + Wh, y0 + s), (x0 + Wc, y0))
            strut((x0, y0 + h), (x0 + Wh, y0 + h - s))
            strut((x0 + Wh, y0 + h - s), (x0 + Wc, y0 + h))
    lattice = union(struts)
    nodes = union([cyl(w * 0.9, t, seg=24).translate([i * Wc + (j % 2) * Wh, j * (h - s) + k, 0])
                   for j in range(rows) for i in range(cols + 1) for k in (0, h)])
    lattice = lattice + nodes
    bb = lattice.bounding_box()
    lattice = lattice.translate([-(bb[0] + bb[3]) / 2, -(bb[1] + bb[4]) / 2, 0])
    return [("lattice", lattice, "teal")]


# ----------------------------------------------------------- S7 gyroid shell
def s7_gyroid(R=36.0, H=92.0, period=24.0, wall=1.3, edge=1.2):
    k = 2 * math.pi / period

    def sdf(x, y, z):
        g = (math.sin(k * x) * math.cos(k * y) + math.sin(k * y) * math.cos(k * z)
             + math.sin(k * z) * math.cos(k * x))
        return wall / 2 - abs(g) * period / (2 * math.pi) / 1.4   # approx distance
    body = md.Manifold.level_set(sdf, [-R - 2, -R - 2, -2, R + 2, R + 2, H + 2], edge)
    body = (body ^ cyl(R, H)).simplify(0.03)
    rim_top = cyl(R + 1.2, 3).translate([0, 0, H - 3]) - cyl(R - 1.8, 3).translate([0, 0, H - 3])
    base = cyl(R + 1.2, 3) - cyl(R - 1.8, 3)
    floor = cyl(R, 2.0)
    return [("gyroid", body, "blue"), ("rim_top", rim_top, "black"),
            ("base", base + floor, "black")]


# ----------------------------------------------------- S8 compliant tweezer clip
def s8_compliant_clip(closed=False):
    L, depth = 70.0, 10.0
    arm_t = 2.6
    hinge_t, hinge_r = 1.0, 8.0
    open_gap = 0.0 if closed else 12.0
    parts = []
    for sgn in (1, -1):
        y_tip = sgn * (open_gap / 2 + arm_t / 2)
        y_root = sgn * (hinge_r - hinge_t / 2)
        ang = math.degrees(math.atan2(y_tip - y_root, L))
        length = math.hypot(L, y_tip - y_root)
        arm = box(length, arm_t, depth).rotate([0, 0, ang]).translate([L / 2, (y_tip + y_root) / 2, depth / 2])
        pad = box(14, 3.5, depth).rotate([0, 0, ang]).translate([L * 0.55, (y_tip + y_root) / 2 + sgn * 2.4, depth / 2])
        pad = pad - box(14, 3.5, depth).translate([L * 0.55, (y_tip + y_root) / 2 + sgn * 6, depth / 2])
        # serrated tip
        tip = box(9, arm_t + 0.5, depth).translate([L - 4.5, y_tip - sgn * 0.6, depth / 2])
        teeth = union([box(1.0, 1.0, depth).rotate([0, 0, 45]).translate([L - 8 + 2 * i, y_tip - sgn * 1.9, depth / 2])
                       for i in range(4)])
        parts.append(arm + pad + tip + teeth)
    flex = (cyl(hinge_r, depth) - cyl(hinge_r - hinge_t, depth)) ^ box(hinge_r * 2, hinge_r * 2, depth * 2).translate([-hinge_r, 0, 0])
    body = parts[0] + parts[1] + flex
    return [("clip", body, "orange")]


# ------------------------------------------------------------ S9 chainmail
def s9_chainmail(rows=9, cols=7, R=5.0, r=0.9, tilt=35.0, dx=12.5, dy=3.5):
    """European 4-in-1 laid out for print-in-place. Rows alternate tilt; with
    these values every ring links its four neighbours (Gauss linking number 1)
    and the wire centrelines stay 2.2 mm apart, i.e. 0.4 mm surface gap."""
    rings = []
    for j in range(rows):
        for i in range(cols):
            ring = torus(R, r, seg=48, rseg=12).rotate([tilt * (1 if j % 2 == 0 else -1), 0, 0])
            x = i * dx + (j % 2) * dx / 2
            rings.append((f"ring_{j}_{i}", ring.translate([x, j * dy, R * math.sin(math.radians(tilt)) + r * 1.05]),
                          "white" if j % 2 == 0 else "teal"))
    # center the sheet
    xs = [p.bounding_box() for _, p, _ in rings]
    cx = (min(b[0] for b in xs) + max(b[3] for b in xs)) / 2
    cy = (min(b[1] for b in xs) + max(b[4] for b in xs)) / 2
    return [(n, p.translate([-cx, -cy, 0]), c) for n, p, c in rings]


# ------------------------------------------------------- S10 planetary gears
def gear_profile(z, m, internal=False, clearance=0.0, pressure=20.0, pts=6):
    """Simple involute-ish gear as a polygon. Adequate for visual review."""
    rp = m * z / 2
    ra = rp + m + (clearance if internal else -clearance * 0)
    rf = rp - 1.25 * m - clearance
    if internal:
        ra, rf = rp - m - clearance, rp + 1.25 * m + clearance
    rb = rp * math.cos(math.radians(pressure))
    poly = []
    half_tooth = math.pi / (2 * z)

    def inv(rr):
        aa = math.acos(min(1, rb / rr))
        return math.tan(aa) - aa
    inv_p = inv(rp)
    for tooth in range(z):
        base = 2 * math.pi * tooth / z
        rs = np.linspace(max(rb, min(rf, ra)), max(rf, ra), pts)
        if not internal:
            rs = np.linspace(max(rb, rf), ra, pts)
            side1, side2 = [], []
            for rr in rs:
                th = half_tooth + inv_p - inv(rr)
                side1.append((rr * math.cos(base - th), rr * math.sin(base - th)))
                side2.append((rr * math.cos(base + th), rr * math.sin(base + th)))
            root_ang = base - 2 * math.pi / z / 2
            poly.append((rf * math.cos(root_ang + 0.05), rf * math.sin(root_ang + 0.05)))
            poly.append((rf * math.cos(base - half_tooth - inv_p - 0.02), rf * math.sin(base - half_tooth - inv_p - 0.02)))
            poly += side1 + side2[::-1]
        else:
            rs = np.linspace(ra, rf, pts)
            side1, side2 = [], []
            for rr in rs:
                th = half_tooth + inv_p - inv(max(rr, rb))
                side1.append((rr * math.cos(base - th), rr * math.sin(base - th)))
                side2.append((rr * math.cos(base + th), rr * math.sin(base + th)))
            poly += side1[::-1] + side2
    return md.CrossSection([poly])


def s10_planetary(theta=0.0):
    m, zs, zp = 1.5, 12, 12
    zr = zs + 2 * zp
    t = 8.0
    rs, rp = m * zs / 2, m * zp / 2
    rc = rs + rp
    sun = md.Manifold.extrude(gear_profile(zs, m), t)
    sun = sun + cyl(9, 3).translate([0, 0, t]) - cyl(2.2, 30, center=True)
    ring_inner = md.Manifold.extrude(gear_profile(zr, m, internal=True, clearance=0.15), t)
    ring = cyl(rc + rp + 9, t, seg=6) - ring_inner
    ring = ring.rotate([0, 0, 30])
    planets = []
    pins = []
    for k in range(3):
        ang = math.radians(120 * k + theta)
        p = md.Manifold.extrude(gear_profile(zp, m), t)
        p = p.rotate([0, 0, 180 / zp + 0]).translate([rc * math.cos(ang), rc * math.sin(ang), 0])
        p -= cyl(2.4, 30, center=True).translate([rc * math.cos(ang), rc * math.sin(ang), 0])
        planets.append(p)
        pins.append(cyl(2.1, t + 6).translate([rc * math.cos(ang), rc * math.sin(ang), -3]))
    carrier_lo = union([cyl(6, 2.4).translate([rc * math.cos(math.radians(120 * k + theta)),
                                              rc * math.sin(math.radians(120 * k + theta)), -2.6]) for k in range(3)])
    spokes = union([box(rc, 6, 2.4).rotate([0, 0, 120 * k + theta])
                    .translate([rc / 2 * math.cos(math.radians(120 * k + theta)),
                                rc / 2 * math.sin(math.radians(120 * k + theta)), -1.3]) for k in range(3)])
    carrier_lo = carrier_lo + spokes + cyl(7, 2.4).translate([0, 0, -2.6])
    carrier_lo = carrier_lo - cyl(2.6, 10, center=True).translate([0, 0, -1])
    carrier_hi = union([cyl(6, 2.4).translate([rc * math.cos(math.radians(120 * k + theta)),
                                              rc * math.sin(math.radians(120 * k + theta)), t + 0.4]) for k in range(3)])
    carrier_hi = carrier_hi + union([cyl(3, 8).translate([rc * math.cos(math.radians(120 * k + theta)),
                                                        rc * math.sin(math.radians(120 * k + theta)), t + 0.4]) for k in range(3)])
    return [("sun", sun, "orange"), ("ring", ring, "blue"), ("planets", union(planets), "white"),
            ("pins", union(pins), "black"), ("carrier_low", carrier_lo, "black"),
            ("carrier_high", carrier_hi, "black")]


# ------------------------------------------------------------------ registry
CONCEPTS = {
    "S1": ("分割球スピナー", "segmented sphere spinner", {"main": lambda: s1_segmented_spinner()}),
    "S2": ("遠心で開く球", "centrifugal opening ball",
           {"closed": lambda: s2_centrifugal_ball(0.0), "open": lambda: s2_centrifugal_ball(32.0)}),
    "S3": ("入れ子ジンバル", "nested gimbal", {"main": lambda: s3_gimbal()}),
    "S4": ("カレイドサイクル", "kaleidocycle",
           {"state_a": lambda: s4_kaleidocycle(1.0), "state_b": lambda: s4_kaleidocycle(1.2)}),
    "S5": ("テンセグリティ小物置き", "tensegrity stand", {"main": lambda: s5_tensegrity()}),
    "S6": ("オーゼティック格子", "auxetic lattice",
           {"rest": lambda: s6_auxetic(0.0), "stretched": lambda: s6_auxetic(1.0)}),
    "S7": ("ジャイロイド殻", "gyroid shell", {"main": lambda: s7_gyroid()}),
    "S8": ("一体ヒンジのクリップ", "compliant clip",
           {"open": lambda: s8_compliant_clip(False), "closed": lambda: s8_compliant_clip(True)}),
    "S9": ("一体印刷の鎖帷子", "print-in-place chainmail", {"main": lambda: s9_chainmail()}),
    "S10": ("遊星歯車の回し物", "planetary gear fidget", {"main": lambda: s10_planetary()}),
}


def build_all(ids=None):
    result = {}
    for cid, (ja, en, states) in CONCEPTS.items():
        if ids and cid not in ids:
            continue
        result[cid] = {"ja": ja, "en": en, "states": {k: f() for k, f in states.items()}}
    return result


def export(models):
    report = {}
    for cid, m in models.items():
        d = OUT / cid.lower()
        d.mkdir(parents=True, exist_ok=True)
        first_state = next(iter(m["states"]))
        report[cid] = {"name": m["ja"], "parts": {}}
        parts = m["states"][first_state]
        if cid == "S9":                      # one print-in-place sheet, not 63 files
            parts = [("sheet", md.Manifold.compose([p for _, p, _ in parts]), "white")]
        for name, solid, color in parts:
            if name.endswith("_ghost"):
                continue
            mesh = to_mesh(solid)
            mesh.export(d / f"{name}.stl")
            bb = mesh.bounds
            report[cid]["parts"][name] = {
                "color": color, "volume_cm3": round(float(mesh.volume) / 1000, 2),
                "size_mm": [round(float(v), 1) for v in (bb[1] - bb[0])],
                "watertight": bool(mesh.is_watertight), "triangles": int(len(mesh.faces)),
            }
    (OUT / "mesh-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    import sys
    ids = sys.argv[1:] or None
    models = build_all(ids)
    rep = export(models)
    for cid, r in rep.items():
        print(cid, r["name"], {k: (v["size_mm"], v["volume_cm3"]) for k, v in r["parts"].items()})
