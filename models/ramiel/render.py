"""Render actual model meshes with flat opaque shading for geometric review."""
import json
import math
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parent / ".mpl-cache"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from build import ROOT, build_models, to_mesh, part_color


def draw(ax, pieces, elev=15, azim=-67, mono=False, exploded=False):
    meshes = []
    for name, solid in pieces:
        mesh = to_mesh(solid)
        if exploded:
            if name == "default_upper":
                mesh.apply_translation([0, 0, 22])
            elif name == "star_body":
                mesh.apply_translation([0, -28, 0])
            elif name == "red_core":
                mesh.apply_translation([0, -40, 0])
        meshes.append((name, mesh))
    # Orthographic software rasterizer with a per-pixel depth buffer. This avoids
    # painter-sort errors between touching assemblies or a core inside its seat.
    el, az = np.deg2rad([elev, azim])
    eye = np.array([np.cos(el)*np.cos(az), np.cos(el)*np.sin(az), np.sin(el)])
    right = np.cross([0., 0., 1.], eye); right /= np.linalg.norm(right)
    up = np.cross(eye, right)
    basis = np.array([right, up, eye]).T
    all_vertices = np.vstack([m.vertices for _, m in meshes]) @ basis
    lo, hi = all_vertices.min(axis=0), all_vertices.max(axis=0)
    center = (lo + hi)/2
    width, height = 1000, 1000
    scale = min((width-100)/(hi[0]-lo[0]), (height-100)/(hi[1]-lo[1]))
    rgb = np.empty((height, width, 3), dtype=np.uint8); rgb[:] = [11, 18, 32]
    depth = np.full((height, width), -np.inf)
    light = eye * .75 + up * .9 - right * .35; light /= np.linalg.norm(light)
    for name, mesh in meshes:
        projected = mesh.vertices @ basis
        projected[:, 0] = (projected[:, 0]-center[0])*scale + width/2
        projected[:, 1] = -(projected[:, 1]-center[1])*scale + height/2
        base = np.array([.76, .79, .84]) if mono else np.asarray(part_color(name)[:3])/255
        strength = .47 + .53*np.maximum(0, mesh.face_normals @ light)
        colors = np.clip(strength[:, None]*base*255, 0, 255).astype(np.uint8)
        for index, f in enumerate(mesh.faces):
            a, b, c = projected[f]
            xmin = max(0, int(np.floor(min(a[0], b[0], c[0]))))
            xmax = min(width-1, int(np.ceil(max(a[0], b[0], c[0]))))
            ymin = max(0, int(np.floor(min(a[1], b[1], c[1]))))
            ymax = min(height-1, int(np.ceil(max(a[1], b[1], c[1]))))
            if xmin > xmax or ymin > ymax:
                continue
            denom = (b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
            if abs(denom) < 1e-10:
                continue
            ys, xs = np.mgrid[ymin:ymax+1, xmin:xmax+1]
            xs, ys = xs+.5, ys+.5
            u = ((b[1]-c[1])*(xs-c[0])+(c[0]-b[0])*(ys-c[1]))/denom
            v = ((c[1]-a[1])*(xs-c[0])+(a[0]-c[0])*(ys-c[1]))/denom
            w = 1-u-v
            z = u*a[2]+v*b[2]+w*c[2]
            old = depth[ymin:ymax+1, xmin:xmax+1]
            mask = (u >= -1e-8) & (v >= -1e-8) & (w >= -1e-8) & (z > old)
            old[mask] = z[mask]
            rgb[ymin:ymax+1, xmin:xmax+1][mask] = colors[index]
    ax.imshow(rgb)
    ax.set_axis_off()
    ax.set_facecolor("#0b1220")


def main():
    cfg = json.loads((ROOT/"design.json").read_text())
    model = build_models(cfg)
    out = ROOT/"output"
    fig = plt.figure(figsize=(15, 9), facecolor="#0b1220")
    for i, (key, title, sub) in enumerate([
        ("default", "01  /  OCTAHEDRON", "100 mm body height · hollow one-piece body"),
        ("star", "02  /  STAR FORM", "150 mm width · photo-based shell + 3 mm bead")]):
        ax = fig.add_subplot(1, 2, i+1)
        draw(ax, model["assemblies"][key], elev=14 if key=="star" else 13,
             azim=-72 if key=="star" else -58)
        ax.set_title(title, color="#eff4ff", fontsize=15, pad=-12, loc="left")
        fig.text(.08+.48*i, .14, sub, color="#b9c6dc", fontsize=11)
    fig.text(.06, .94, "RAMIEL / DEFAULT V4 + STAR V6", color="#eff4ff", fontsize=22, weight="bold")
    fig.text(.06, .89, "Geometry preview • no LED • opaque shading", color="#8ca6cb", fontsize=12)
    fig.text(.06, .06, "Star reconstructed from reference photos; rear dimensions estimated. Translucency is not simulated.",
             color="#8ca6cb", fontsize=10)
    fig.subplots_adjust(left=.01, right=.99, bottom=.12, top=.84, wspace=-.12)
    fig.savefig(out/"preview.png", dpi=160, facecolor=fig.get_facecolor())
    plt.close(fig)

    fig = plt.figure(figsize=(16, 10), facecolor="#0b1220")
    views = [("default", "DEFAULT / FRONT", 0, -90, False),
             ("default", "DEFAULT / CUTAWAY", 28, -55, True),
             ("star", "STAR / FRONT", model["star_display_tilt"], -90, False),
             ("star", "STAR / SIDE", 25, -10, False),
             ("star", "STAR / REAR", 35, 90, False),
             ("star", "STAR / ASSEMBLY", 15, -55, True)]
    for i, (key, title, elev, azim, exploded) in enumerate(views):
        ax = fig.add_subplot(2, 3, i+1)
        pieces = model["assemblies"][key]
        if key == "default" and exploded:
            pieces = [(n, s.trim_by_plane([0, 1, 0], 0)) for n, s in pieces]
        draw(ax, pieces, elev, azim, mono=True, exploded=exploded)
        ax.set_title(title, color="#e4eaf6", fontsize=11, pad=-10)
    fig.suptitle("SOLID GEOMETRY REVIEW / actual exported geometry", color="#eff4ff", fontsize=17, y=.98)
    fig.text(.04, .02, "Uniform material exposes the geometry. Joint fit, thin details and physical balance still require prototype prints.",
             color="#99adca", fontsize=10)
    fig.subplots_adjust(left=0, right=1, bottom=.04, top=.94, wspace=-.1, hspace=.02)
    fig.savefig(out/"solid-review.png", dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    print("Wrote output/preview.png and output/solid-review.png")
    render_star(model)


def render_star(model):
    out = ROOT / "printing/star-v6"
    out.mkdir(parents=True, exist_ok=True)
    pieces = model["assemblies"]["star"]
    tilt = model["star_display_tilt"]
    fig = plt.figure(figsize=(16, 10), facecolor="#0b1220")
    views = [("FRONT / recessed core", tilt, -90),
             ("SIDE / forward arms + compact rear", 25, -10), ("REAR", 35, 90),
             ("TOP / fivefold throat", 55, -90)]
    for i, (title, elev, azim) in enumerate(views):
        ax = fig.add_subplot(2, 2, i+1)
        draw(ax, pieces, elev, azim)
        ax.set_title(title, color="#eff4ff", fontsize=13)
    fig.suptitle("RAMIEL / FORWARD ARMS + CITY / STAR V6", color="#eff4ff", fontsize=20)
    fig.text(.04, .02, "Blue shell + 3 mm red bead + conforming black city base. Opaque CAD shading; rear dimensions estimated from photos.",
             color="#8ca6cb", fontsize=10)
    fig.subplots_adjust(top=.92, bottom=.06, wspace=-.06, hspace=.04)
    fig.savefig(out / "star-design.png", dpi=135)
    plt.close(fig)

    # Crop the real solid to show the throat, and section it to expose the void.
    from build import box
    cfg = json.loads((ROOT / "design.json").read_text())
    body = model["parts"]["star_body"]
    bead = model["parts"]["red_core"].translate([0, 0, cfg["star_bead_center_z"]])
    close = [("star_body", body ^ box([72, 72, 60], (-36, -36, -15))), ("red_core", bead)]
    cut = [("star_body", body.trim_by_plane([1, 0, 0], 0)), ("red_core", bead)]
    fig = plt.figure(figsize=(14, 7), facecolor="#0b1220")
    for i, (title, parts, elev, azim) in enumerate([
            ("CENTRE DETAIL / open throat + bead seat", close, 87, -90),
            ("CUTAWAY / 1.2 mm shell, empty interior", cut, 15, -165)]):
        ax = fig.add_subplot(1, 2, i+1)
        draw(ax, parts, elev, azim)
        ax.set_title(title, color="#eff4ff", fontsize=13)
    fig.suptitle("STAR V6 / CENTRAL STRUCTURE", color="#eff4ff", fontsize=20)
    fig.text(.04, .04, "Actual CAD sections; exposed cut edges are for explanation only. Red inner faces in the figure photos would need an optional painted finish.",
             color="#8ca6cb", fontsize=10)
    fig.subplots_adjust(top=.88, bottom=.12, wspace=.04)
    fig.savefig(out / "centre-detail.png", dpi=140)
    plt.close(fig)


if __name__ == "__main__":
    main()
