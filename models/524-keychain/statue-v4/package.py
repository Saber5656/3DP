"""Regenerate artifact-manifest.json and the distributable design-pack ZIP."""
import hashlib
import json
import os
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ZIP_PATH = ROOT / 'output' / '524-keychain-statue-v4-design-pack.zip'
TOP = '524-keychain-statue-v4'
DIRS = {'output': {'.3mf', '.stl', '.glb', '.png', '.json'},
        'source': None,
        'slicing': {'.3mf', '.log', '.json', '.png'},
        'tests': {'.py'}}
FILES = ['README.md', 'requirements.txt', 'build.py', 'inspect_slice.py',
         'render.py', 'slice.py', 'wood_body.py', 'balance.py', 'package.py']
SKIP_PARTS = {'runtime', 'presets', '__pycache__'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def collect():
    found = [ROOT / f for f in FILES if (ROOT / f).is_file()]
    for d, exts in DIRS.items():
        for p in (ROOT / d).rglob('*') if (ROOT / d).is_dir() else []:
            rel = p.relative_to(ROOT)
            if (p.is_file() and not SKIP_PARTS & set(rel.parts)
                    and p.suffix != '.zip' and p.name != '.DS_Store'
                    and (exts is None or p.suffix.lower() in exts)):
                found.append(p)
    return sorted(set(found))


def entry(p):
    data = p.read_bytes()
    return {'path': p.relative_to(ROOT).as_posix(), 'sha256': sha(data), 'bytes': len(data)}


def write_json(path, files):
    path.write_text(json.dumps({'files': files}, indent=2) + '\n')


def in_pack(rel):
    # slicing 3mf/gcode hold unverified provisional G-code
    return not (rel.startswith('slicing/') and rel.endswith(('.3mf', '.gcode')))


def main():
    files = collect()
    write_json(ROOT / 'artifact-manifest.json',
               [e for e in map(entry, files) if e['path'] != 'artifact-manifest.json'])
    packed = [p for p in files if in_pack(p.relative_to(ROOT).as_posix())
              and p.name != 'artifact-manifest.json']
    entries = [entry(p) for p in packed]
    tmp = ZIP_PATH.with_name(ZIP_PATH.name + '.tmp')
    try:
        with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as z:
            for p, e in zip(packed, entries):
                z.write(p, f"{TOP}/{e['path']}")
            z.writestr(f'{TOP}/package-manifest.json',
                       json.dumps({'files': entries}, indent=2) + '\n')
        with zipfile.ZipFile(tmp) as z:
            bad = z.testzip()
            if bad:
                raise RuntimeError(f'corrupt member: {bad}')
            for e in entries:
                if sha(z.read(f"{TOP}/{e['path']}")) != e['sha256']:
                    raise RuntimeError(f"hash mismatch: {e['path']}")
        os.replace(tmp, ZIP_PATH)
    finally:
        tmp.unlink(missing_ok=True)
    print(f'{ZIP_PATH} ({len(entries)} files)')


if __name__ == '__main__':
    main()
