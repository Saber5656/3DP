"""Render the concept solids to PNG for visual review (painter-sorted triangles).

Run from this directory: python render.py [S1 S2 ...]
Writes output/<id>.png (per concept, several views/states) and output/overview.png.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from build import COLORS, CONCEPTS, OUT, build_all, to_mesh

BG = (11, 18, 32)
FG = (239, 244, 255)
SUB = (140, 166, 203)


def _font(size):
    for path in [str(Path.home() / ".fonts/NotoSansJP-VF.ttf"),
                 "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def render(parts, elev=22, azim=-55, size=(900, 900), margin=70, persp=0.0):
    """Orthographic render, triangles painter-sorted back to front."""
    el, az = np.deg2rad([elev, azim])
    eye = np.array([np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), np.sin(el)])
    right = np.cross([0., 0., 1.], eye)
    right /= np.linalg.norm(right)
    up = np.cross(eye, right)
    basis = np.array([right, up, eye]).T
    light = eye * .6 + up * .9 - right * .45
    light /= np.linalg.norm(light)

    tris, cols, depth = [], [], []
    for name, solid, color in parts:
        mesh = to_mesh(solid)
        if len(mesh.faces) == 0:
            continue
        v = mesh.vertices @ basis
        f = mesh.faces
        base = np.asarray(COLORS[color], float) / 255
        alpha = 0.35 if name.endswith("_ghost") else 1.0
        shade = 0.42 + 0.58 * np.clip(mesh.face_normals @ light, 0, 1)
        rgb = np.clip(shade[:, None] * base * 255, 0, 255)
        rgb = rgb * alpha + np.array(BG) * (1 - alpha)
        tris.append(v[f])
        cols.append(rgb.astype(np.uint8))
        depth.append(v[f][:, :, 2].mean(axis=1))
    T = np.concatenate(tris)
    C = np.concatenate(cols)
    D = np.concatenate(depth)
    lo, hi = T[:, :, :2].reshape(-1, 2).min(0), T[:, :, :2].reshape(-1, 2).max(0)
    center = (lo + hi) / 2
    W, H = size
    scale = min((W - 2 * margin) / max(hi[0] - lo[0], 1e-6), (H - 2 * margin) / max(hi[1] - lo[1], 1e-6))
    img = Image.new("RGB", size, BG)
    draw = ImageDraw.Draw(img)
    order = np.argsort(D)
    P = T[:, :, :2].copy()
    P[:, :, 0] = (P[:, :, 0] - center[0]) * scale + W / 2
    P[:, :, 1] = -(P[:, :, 1] - center[1]) * scale + H / 2
    for i in order:
        draw.polygon([tuple(p) for p in P[i]], fill=tuple(int(c) for c in C[i]))
    return img


def label(img, title, sub=None):
    d = ImageDraw.Draw(img)
    d.text((22, 16), title, fill=FG, font=_font(26))
    if sub:
        d.text((22, 50), sub, fill=SUB, font=_font(17))
    return img


VIEWS = {
    "S1": [("main", 20, -50, "iso"), ("main", 0, -90, "front"), ("main", 70, -90, "top")],
    "S2": [("closed", 18, -50, "at rest"), ("open", 18, -50, "spinning - petals open"), ("open", 65, -90, "spinning - top")],
    "S3": [("main", 22, -50, "iso"), ("main", 0, -90, "front"), ("main", 20, -20, "side")],
    "S4": [("state_b", 30, -60, "turning - state B"), ("state_a", 30, -60, "turning - state A"), ("state_b", 80, -90, "top")],
    "S5": [("main", 12, -55, "iso"), ("main", 0, -90, "front"), ("main", 0, 0, "side")],
    "S6": [("rest", 88, -90, "at rest"), ("stretched", 88, -90, "pulled - opens both ways"), ("rest", 35, -60, "iso")],
    "S7": [("main", 15, -55, "iso"), ("main", 0, -90, "front"), ("main", 85, -90, "top")],
    "S8": [("open", 30, -60, "released"), ("closed", 30, -60, "pressed"), ("open", 88, -90, "top")],
    "S9": [("main", 35, -60, "iso"), ("main", 88, -90, "top"), ("main", 5, -90, "edge")],
    "S10": [("main", 35, -60, "iso"), ("main", 88, -90, "top"), ("main", 10, -60, "low")],
}


def sheet(cid, model):
    ja, en = model["ja"], model["en"]
    views = VIEWS[cid]
    tile = 760
    img = Image.new("RGB", (tile * len(views), tile + 90), BG)
    label(img, f"{cid}  {ja}", en)
    for i, (state, elev, azim, name) in enumerate(views):
        r = render(model["states"][state], elev, azim, (tile, tile))
        img.paste(r, (i * tile, 90))
        ImageDraw.Draw(img).text((i * tile + 20, 90 + tile - 40), name, fill=SUB, font=_font(20))
    return img


def main():
    ids = sys.argv[1:] or None
    models = build_all(ids)
    OUT.mkdir(exist_ok=True)
    heroes = {}
    for cid, model in models.items():
        s = sheet(cid, model)
        s.save(OUT / f"{cid.lower()}.png")
        state, elev, azim, _ = VIEWS[cid][0]
        heroes[cid] = render(model["states"][state], elev, azim, (620, 620), margin=50)
        print("wrote", cid)
    if ids is None:
        cols, tile = 5, 620
        rows = (len(heroes) + cols - 1) // cols
        ov = Image.new("RGB", (cols * tile, rows * (tile + 60) + 80), BG)
        label(ov, "STRUCTURAL AESTHETICS / 10 CONCEPTS", "ideal-form solids, concept stage, not yet printed")
        for i, (cid, im) in enumerate(heroes.items()):
            x, y = (i % cols) * tile, 80 + (i // cols) * (tile + 60)
            ov.paste(im, (x, y))
            ImageDraw.Draw(ov).text((x + 18, y + tile + 12), f"{cid}  {models[cid]['ja']}", fill=FG, font=_font(22))
        ov.save(OUT / "overview.png")
        print("wrote overview")


if __name__ == "__main__":
    main()
