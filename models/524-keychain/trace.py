"""Extract faithful shape contours (pixel coords, y down) from source/original-524.jpg."""
import hashlib, json, sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from shapely.geometry import Polygon
from shapely.ops import unary_union
from skimage import measure, draw

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "source" / "original-524.jpg"
TOL = 0.6  # px simplification tolerance (JPEG blur is ~1px)
CENTROIDS = {  # reference colors sampled from the artwork
    "blue": (91, 182, 214), "black": (0, 0, 0), "yellow": (253, 224, 70),
    "white": (247, 247, 247), "orange": (240, 124, 65), "teal": (36, 112, 133),
}


def classify(rgb):
    names = list(CENTROIDS)
    c = np.array([CENTROIDS[n] for n in names], float)
    d = ((rgb[:, :, None, :].astype(float) - c[None, None]) ** 2).sum(-1)
    return names, d.argmin(-1)


def clean(m, r=1):
    m = ndi.binary_opening(m, iterations=r)
    return ndi.binary_closing(m, iterations=r)


def mask_to_polys(mask):
    """Trace mask boundaries at 0.5 iso-level; returns shapely geometry with holes."""
    pad = np.pad(mask.astype(float), 1)
    polys = []
    for c in measure.find_contours(pad, 0.5):
        pts = c[:, ::-1] - 1  # (x, y)
        if len(pts) >= 4:
            p = Polygon(pts).buffer(0)
            if p.area > 4:
                polys.append(p)
    # even-odd assembly: sort by area, nest
    polys.sort(key=lambda p: -p.area)
    shells = []
    for p in polys:
        for s in shells:
            if s["poly"].contains(p.representative_point()):
                s["holes"].append(p) if s["depth"] == 0 else None
                break
        else:
            shells.append({"poly": p, "holes": [], "depth": 0})
    out = []
    for s in shells:
        g = s["poly"]
        for h in s["holes"]:
            g = g.difference(h)
        out.append(g)
    return unary_union(out)


def simplify(g):
    return g.simplify(TOL, preserve_topology=True)


def to_json(g):
    res = []
    for p in (g.geoms if hasattr(g, "geoms") else [g]):
        if p.is_empty:
            continue
        res.append({"exterior": [[round(x, 2), round(y, 2)] for x, y in p.exterior.coords[:-1]],
                    "holes": [[[round(x, 2), round(y, 2)] for x, y in r.coords[:-1]] for r in p.interiors]})
    return res


def raster(g, shape):
    m = np.zeros(shape, bool)
    for p in (g.geoms if hasattr(g, "geoms") else [g]):
        rr, cc = draw.polygon(*zip(*[(y, x) for x, y in p.exterior.coords]), shape=shape)
        m[rr, cc] = True
        for h in p.interiors:
            rr, cc = draw.polygon(*zip(*[(y, x) for x, y in h.coords]), shape=shape)
            m[rr, cc] = False
    return m


def iou(a, b):
    return float((a & b).sum() / max((a | b).sum(), 1))


def median_color(rgb, m):
    inner = ndi.binary_erosion(m, iterations=3)
    if inner.sum() < 20:
        inner = ndi.binary_erosion(m, iterations=1)
    if inner.sum() == 0:
        inner = m
    return [int(v) for v in np.median(rgb[inner], axis=0)]


def trace(path=SRC):
    path = Path(path)
    im = Image.open(path).convert("RGB")
    rgb = np.asarray(im)
    h, w = rgb.shape[:2]
    names, lab = classify(rgb)
    cls = {n: clean(lab == i) for i, n in enumerate(names)}
    non_bg = ~(cls["blue"] | cls["black"])
    non_bg = ndi.binary_opening(non_bg, iterations=1)
    cc, n = ndi.label(non_bg)
    sizes = ndi.sum(non_bg, cc, range(1, n + 1))
    main = int(np.argmax(sizes)) + 1
    body = ndi.binary_fill_holes(cc == main)
    dot_masks = []
    for i in range(1, n + 1):
        if i != main and sizes[i - 1] >= 60:
            dot_masks.append(cc == i)
    dot_masks.sort(key=lambda m: np.argwhere(m)[:, 0].mean())
    white = cls["white"] & body
    white_l, wn = ndi.label(white)
    if wn > 1:
        ws = ndi.sum(white, white_l, range(1, wn + 1))
        white = white_l == (int(np.argmax(ws)) + 1)
    orange = cls["orange"] & body
    ol, on = ndi.label(orange)
    osz = ndi.sum(orange, ol, range(1, on + 1))
    digs = [ol == i for i in np.argsort(-osz)[:3] + 1]
    digs.sort(key=lambda m: np.argwhere(m)[:, 1].mean())
    teal = cls["teal"] & body
    tl, tn = ndi.label(teal)
    tsz = ndi.sum(teal, tl, range(1, tn + 1))
    mouth = tl == (int(np.argmax(tsz)) + 1)

    # white shape includes digit areas (holes filled) so it is the continuous 3-circle outline
    white_full = ndi.binary_fill_holes(white | np.any(digs, axis=0))
    specs = [("body", "body", body, "yellow")]
    specs.append(("white", "white", white_full, "white"))
    for i, m in enumerate(digs):
        specs.append((f"digit{i}", "digit", m, "orange"))
    specs.append(("mouth", "mouth", mouth, "teal"))
    for i, m in enumerate(dot_masks):
        specs.append((f"dot{i}", "dot", m, "yellow"))

    parts, ious = [], {}
    for name, kind, m, _ in specs:
        if kind == "body":
            ref = body & ~white_full & ~mouth & ~np.any(digs, axis=0)
            rgbm = median_color(rgb, ref)
        else:
            rgbm = median_color(rgb, m)
        g = simplify(mask_to_polys(m))
        ious[name] = round(iou(m, raster(g, m.shape)), 4)
        x0, y0, x1, y1 = g.bounds
        parts.append({"name": name, "kind": kind, "median_rgb": rgbm,
                      "hex": "#%02x%02x%02x" % tuple(rgbm),
                      "bounds": [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)],
                      "area_px": round(g.area, 1), "polygons": to_json(g)})
    return {"image": {"file": "source/" + path.name, "width": w, "height": h,
                      "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                      "coords": "pixel, origin top-left, y down"},
            "simplify_tol_px": TOL, "parts": parts, "quality": {"iou": ious}}


if __name__ == "__main__":
    d = trace()
    (ROOT / "source" / "traced-contours.json").write_text(json.dumps(d, separators=(",", ":")))
    print({p["name"]: (p["hex"], p["bounds"]) for p in d["parts"]}, d["quality"])
