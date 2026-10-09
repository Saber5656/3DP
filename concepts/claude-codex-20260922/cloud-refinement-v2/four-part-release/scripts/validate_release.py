"""Validate the 4-part A2/A3 release bundle.

Checks:
- all 8 STLs and 2 assembled 3MFs exist
- each STL is a single watertight (closed) mesh with positive volume
- each assembly's 4 parts combine to a 48 mm tall bounding box
- writes manifest.json with source/copy relative paths, SHA-256, and
  measured dimensions/color/quantity
"""
import hashlib
import json
from pathlib import Path

import trimesh

RELEASE_DIR = Path(__file__).resolve().parent.parent
ROOT = RELEASE_DIR.parent  # cloud-refinement-v2

TARGET_HEIGHT_MM = 48.0
HEIGHT_TOLERANCE_MM = 0.05

PARTS = [
    {
        "design": "A2",
        "part": "body",
        "color": "orange",
        "source": "output/stl/A2_clawd.stl",
        "copy": "four-part-release/stl/A2-body.stl",
    },
    {
        "design": "A2",
        "part": "cloud",
        "color": "white",
        "source": "output/optional-onepiece/A2-v2-cloud-onepiece.stl",
        "copy": "four-part-release/stl/A2-cloud.stl",
    },
    {
        "design": "A2",
        "part": "eye-left",
        "color": "black",
        "source": "output/stl/A2_clawd_eye_1.stl",
        "copy": "four-part-release/stl/A2-eye-left.stl",
    },
    {
        "design": "A2",
        "part": "eye-right",
        "color": "black",
        "source": "output/stl/A2_clawd_eye_2.stl",
        "copy": "four-part-release/stl/A2-eye-right.stl",
    },
    {
        "design": "A3",
        "part": "body",
        "color": "orange",
        "source": "output/stl/A3_clawd.stl",
        "copy": "four-part-release/stl/A3-body.stl",
    },
    {
        "design": "A3",
        "part": "cloud",
        "color": "white",
        "source": "output/optional-onepiece/A3-v2-cloud-onepiece.stl",
        "copy": "four-part-release/stl/A3-cloud.stl",
    },
    {
        "design": "A3",
        "part": "eye-left",
        "color": "black",
        "source": "output/stl/A3_clawd_eye_1.stl",
        "copy": "four-part-release/stl/A3-eye-left.stl",
    },
    {
        "design": "A3",
        "part": "eye-right",
        "color": "black",
        "source": "output/stl/A3_clawd_eye_2.stl",
        "copy": "four-part-release/stl/A3-eye-right.stl",
    },
]

ASSEMBLIES = [
    {
        "design": "A2",
        "source": "output/optional-onepiece/A2-v2-onepiece-assembled.3mf",
        "copy": "four-part-release/assembly/A2-four-part-assembled.3mf",
    },
    {
        "design": "A3",
        "source": "output/optional-onepiece/A3-v2-onepiece-assembled.3mf",
        "copy": "four-part-release/assembly/A3-four-part-assembled.3mf",
    },
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def check_stl(path: Path) -> dict:
    mesh = trimesh.load(path, force="mesh")
    watertight = bool(mesh.is_watertight)
    volume = float(mesh.volume) if watertight else None
    bounds = mesh.bounds
    extents = (bounds[1] - bounds[0]).tolist()
    return {
        "watertight": watertight,
        "single_body": len(mesh.split(only_watertight=False)) == 1,
        "volume_mm3": volume,
        "volume_positive": bool(volume is not None and volume > 0),
        "extents_mm": extents,
        "bounds_mm": bounds.tolist(),
    }


def check_assembly_height(assembly_path: Path) -> dict:
    scene = trimesh.load(assembly_path, force="scene")
    combined = trimesh.util.concatenate(
        [g for g in scene.geometry.values()]
    )
    bounds = combined.bounds
    height = float(bounds[1][2] - bounds[0][2])
    return {
        "part_count": len(scene.geometry),
        "height_mm": height,
        "height_ok": abs(height - TARGET_HEIGHT_MM) <= HEIGHT_TOLERANCE_MM,
    }


def main() -> int:
    manifest = {
        "unit": "mm",
        "target_height_mm": TARGET_HEIGHT_MM,
        "quantity_per_part": 1,
        "parts": [],
        "assemblies": [],
    }
    ok = True

    for spec in PARTS:
        source_path = ROOT / spec["source"]
        copy_path = ROOT / spec["copy"]
        exists = source_path.is_file() and copy_path.is_file()
        entry = {
            "design": spec["design"],
            "part": spec["part"],
            "color": spec["color"],
            "quantity": 1,
            "source_path": spec["source"],
            "copy_path": spec["copy"],
        }
        if not exists:
            entry["error"] = "missing file"
            ok = False
            manifest["parts"].append(entry)
            continue

        entry["source_sha256"] = sha256(source_path)
        entry["copy_sha256"] = sha256(copy_path)
        entry["files_identical"] = entry["source_sha256"] == entry["copy_sha256"]
        ok = ok and entry["files_identical"]

        mesh_check = check_stl(copy_path)
        entry.update(mesh_check)
        ok = ok and mesh_check["watertight"] and mesh_check["single_body"] and mesh_check["volume_positive"]

        manifest["parts"].append(entry)

    for spec in ASSEMBLIES:
        source_path = ROOT / spec["source"]
        copy_path = ROOT / spec["copy"]
        exists = source_path.is_file() and copy_path.is_file()
        entry = {
            "design": spec["design"],
            "source_path": spec["source"],
            "copy_path": spec["copy"],
        }
        if not exists:
            entry["error"] = "missing file"
            ok = False
            manifest["assemblies"].append(entry)
            continue

        entry["source_sha256"] = sha256(source_path)
        entry["copy_sha256"] = sha256(copy_path)
        entry["files_identical"] = entry["source_sha256"] == entry["copy_sha256"]
        ok = ok and entry["files_identical"]

        height_check = check_assembly_height(copy_path)
        entry.update(height_check)
        ok = ok and height_check["part_count"] == 4 and height_check["height_ok"]

        manifest["assemblies"].append(entry)

    manifest["all_checks_passed"] = ok

    out_path = RELEASE_DIR / "manifest.json"
    out_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")

    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    print()
    print("ALL CHECKS PASSED" if ok else "VALIDATION FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
