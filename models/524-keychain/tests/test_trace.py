import hashlib, json, unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from shapely.geometry import Polygon
from shapely.ops import unary_union

import importlib.util

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("trace_524", ROOT / "trace.py")  # stdlib 'trace' shadows plain import
T = importlib.util.module_from_spec(_spec)
IMG = ROOT / "source" / "original-524.jpg"

_spec.loader.exec_module(T) if (ROOT / "trace.py").exists() else None


def load_parts():
    return T.trace(IMG)["parts"]


def poly(part):
    return unary_union([Polygon(p["exterior"], p["holes"]).buffer(0) for p in part["polygons"]])


def by(parts, kind):
    return [p for p in parts if p["kind"] == kind]


class TraceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = T.trace(IMG)
        cls.parts = cls.data["parts"]

    def test_counts(self):
        for kind, n in [("body", 1), ("white", 1), ("digit", 3), ("mouth", 1), ("dot", 2)]:
            self.assertEqual(len(by(self.parts, kind)), n, kind)

    def test_metadata(self):
        self.assertEqual(self.data["image"]["sha256"], hashlib.sha256(IMG.read_bytes()).hexdigest())
        with Image.open(IMG) as image:
            self.assertEqual((self.data["image"]["width"], self.data["image"]["height"]), image.size)
        for p in self.parts:
            self.assertEqual(len(p["median_rgb"]), 3)
            self.assertRegex(p["hex"], r"^#[0-9a-f]{6}$")
            self.assertTrue(p["polygons"])

    def test_containment(self):
        body = poly(by(self.parts, "body")[0]).buffer(1.5)
        for p in self.parts:
            if p["kind"] in ("white", "digit", "mouth"):
                self.assertTrue(body.contains(poly(p)), p["name"])
        white = poly(by(self.parts, "white")[0])
        for d in by(self.parts, "digit"):
            self.assertLess(poly(d).difference(white.buffer(1.5)).area, 1.0)
        mouth = poly(by(self.parts, "mouth")[0])
        self.assertFalse(mouth.intersects(white))

    def test_dots_separate_and_right_bottom(self):
        body = poly(by(self.parts, "body")[0])
        for d in by(self.parts, "dot"):
            self.assertFalse(body.intersects(poly(d)))
            cx, cy = poly(d).centroid.coords[0]
            self.assertGreater(cx, 400); self.assertGreater(cy, 550)

    def test_digit_order_and_colors(self):
        xs = [poly(d).centroid.x for d in by(self.parts, "digit")]
        self.assertEqual(xs, sorted(xs))
        r, g, b = by(self.parts, "digit")[0]["median_rgb"]
        self.assertTrue(r > 200 and g < 150 and b < 100)
        r, g, b = by(self.parts, "mouth")[0]["median_rgb"]
        self.assertTrue(r < 80 and b > g * 0.9 and g > 80)

    def test_excludes_blue_and_black(self):
        body = poly(by(self.parts, "body")[0])
        im = np.asarray(Image.open(IMG).convert("RGB"))
        for (x, y) in [(5, 5), (20, 10), (5, 690), (650, 690), (40, 300)]:
            from shapely.geometry import Point
            self.assertFalse(body.contains(Point(x, y)), (x, y))

    def test_iou(self):
        ious = self.data["quality"]["iou"]
        for k, v in ious.items():
            self.assertGreater(v, 0.98, k)
        # independent re-raster check for body
        w, h = self.data["image"]["width"], self.data["image"]["height"]
        m = Image.new("L", (w, h), 0)
        ImageDraw.Draw(m).polygon([tuple(q) for q in by(self.parts, "body")[0]["polygons"][0]["exterior"]], fill=1)
        self.assertGreater(np.asarray(m).sum(), 100000)


if __name__ == "__main__":
    unittest.main()
