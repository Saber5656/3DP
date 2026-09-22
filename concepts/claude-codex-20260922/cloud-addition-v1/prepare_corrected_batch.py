"""Plan A1–A4 + B4 + D3; --slice explicitly enables private offline slicing.

Source STLs, the previous production tree and its ZIP are never modified. Physical
filament slots are deliberately absent: color grouping is not device allocation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parent
DESIGN_IDS = ('A1', 'A2', 'A3', 'A4', 'B4', 'D3')
NEW_DESIGNS = frozenset(DESIGN_IDS[:4])
EXPECTED_COUNTS = {'A1': 4, 'A2': 4, 'A3': 4, 'A4': 4, 'B4': 7, 'D3': 5}
COLOR_KEYS = ('white', 'orange', 'black', 'translucent_blue')
EXPECTED_COLOR_COUNTS = {'white': 7, 'orange': 6, 'black': 14, 'translucent_blue': 1}


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _private_json(path, data, *, exclusive=False):
    path = Path(path)
    value = json.dumps(data, indent=2, ensure_ascii=False) + '\n'
    if exclusive:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w') as handle:
            handle.write(value)
        return
    descriptor, temporary = tempfile.mkstemp(prefix='.batch-json-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w') as handle:
            handle.write(value)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _read_manifest(path):
    path = Path(path).resolve()
    if path.parent.name != 'output':
        raise ValueError('Manifest must be output/manifest.json within its source project')
    root = path.parent.parent
    data = json.loads(path.read_text())
    if data.get('unit') != 'mm' or data.get('target_height_mm') != 48:
        raise ValueError('Expected millimetres and the agreed 48 mm target height')
    models = {}
    for model in data.get('models', []):
        ident = model['id']
        if ident in models:
            raise ValueError(f'Duplicate model ID: {ident}')
        if type(model.get('quantity')) is not int or model['quantity'] != 1:
            raise ValueError(f'Expected quantity one: {ident}')
        if model.get('height_mm') != 48:
            raise ValueError(f'Expected 48 mm model height: {ident}')
        if type(model.get('parts')) is not int or model['parts'] <= 0:
            raise ValueError(f'Invalid declared part count: {ident}')
        models[ident] = model
    if not models:
        raise ValueError('Manifest has no models')
    selected = data.get('selected_ids', [])
    if len(selected) != len(set(selected)) or set(selected) != set(models):
        raise ValueError('Manifest selected_ids and model IDs disagree')
    rows = []
    ids = set()
    paths = set()
    for part in data.get('parts', []):
        ident = part['id']
        if ident in ids:
            raise ValueError(f'Duplicate part ID: {ident}')
        ids.add(ident)
        design = part.get('design')
        if design not in models or not ident.startswith(design + '_'):
            raise ValueError(f'Unknown or inconsistent design for part: {ident}')
        if type(part.get('count')) is not int or part['count'] != 1:
            raise ValueError(f'Expected one copy of each part: {ident}')
        if type(part.get('support_recommended')) is not bool:
            raise ValueError(f'Support flag must be boolean: {ident}')
        relative = Path(part['stl'])
        actual = (root / relative).resolve()
        if relative.is_absolute() or not actual.is_relative_to(root):
            raise ValueError(f'STL must remain within its source project: {ident}')
        if actual in paths:
            raise ValueError(f'Duplicate STL path: {ident}')
        paths.add(actual)
        if actual.suffix.lower() != '.stl' or not actual.is_file():
            raise FileNotFoundError(f'Missing STL: {actual}')
        expected_hash = part.get('sha256')
        if not isinstance(expected_hash, str) or _sha256(actual) != expected_hash:
            raise ValueError(f'SHA256 mismatch for STL: {ident}')
        rows.append({**part, 'stl_path': str(actual), 'source_manifest': str(path)})
    for ident, model in models.items():
        if sum(row['design'] == ident for row in rows) != model['parts']:
            raise ValueError(f'Declared and actual part count differ: {ident}')
    return models, rows


def build_batch_plan(new_manifest, old_manifest):
    """Validate both manifests, then select exactly six designs and 28 parts."""
    new_manifest = Path(new_manifest).resolve()
    old_manifest = Path(old_manifest).resolve()
    new_models, new_parts = _read_manifest(new_manifest)
    old_models, old_parts = _read_manifest(old_manifest)
    if set(new_models) != NEW_DESIGNS:
        raise ValueError('New manifest must contain exactly A1, A2, A3 and A4')
    if not {'B4', 'D3'} <= set(old_models):
        raise ValueError('Previous manifest is missing B4 or D3')
    source = {**new_models, **{key: old_models[key] for key in ('B4', 'D3')}}
    for ident in DESIGN_IDS:
        if source[ident]['parts'] != EXPECTED_COUNTS[ident]:
            raise ValueError(f'Unexpected part count for {ident}: expected {EXPECTED_COUNTS[ident]}')
    selected = new_parts + [part for part in old_parts if part['design'] in {'B4', 'D3'}]
    if len(selected) != 28 or len({part['id'] for part in selected}) != 28:
        raise ValueError('Expected 28 unique selected parts')
    if len({part['stl_path'] for part in selected}) != 28:
        raise ValueError('Duplicate STL paths across source manifests')
    for part in selected:
        if part['color'] not in COLOR_KEYS:
            raise ValueError(f'Unexpected corrected-batch material color: {part["color"]}')
    plates = []
    for color in COLOR_KEYS:
        parts = sorted((part for part in selected if part['color'] == color), key=lambda part: part['id'])
        if len(parts) != EXPECTED_COLOR_COUNTS[color]:
            raise ValueError(f'Unexpected part count for color {color}: expected {EXPECTED_COLOR_COUNTS[color]}')
        plates.append({'color_key': color, 'part_count': len(parts),
                       'support': any(part['support_recommended'] for part in parts),
                       'output_name': color + '.3mf', 'parts': parts})
    return {'schema_version': 1, 'design_ids': list(DESIGN_IDS), 'part_count': len(selected),
            'target_height_mm': 48, 'excluded_previous_designs': ['D1', 'D2', 'D4'],
            'plates': plates, 'physical_slot_binding': 'NOT_SET', 'device_sent': False,
            'sources': [{'manifest': str(path), 'sha256': _sha256(path)}
                        for path in (new_manifest, old_manifest)],
            'scope': 'Color-separated offline plates; no printer connection, AMS/Ext allocation or inventory update.'}


def verify_preserved_files(preserved_file):
    """Check the parent's pre-addition artifact baseline before creating any new one.

    Its documented exclusions are only __pycache__ and slice-work. This verifies
    complete artifact membership too, so a newly added legacy artifact is detected.
    """
    preserved_file = Path(preserved_file).resolve()
    project = preserved_file.parent.parent
    old_root = project / 'production-v1'
    archive = project / 'claude-codex-48mm.zip'
    expected = json.loads(preserved_file.read_text())
    if not isinstance(expected, dict) or archive.name not in expected:
        raise ValueError('Historical preservation baseline must include the old ZIP')
    for name, digest in expected.items():
        relative = Path(name)
        if (relative.is_absolute() or '..' in relative.parts or
                (name != archive.name and (not relative.parts or relative.parts[0] != 'production-v1'))):
            raise ValueError('Historical baseline contains an unexpected preservation path')
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError('Historical baseline contains an invalid SHA256')
    current = {str(path.relative_to(project)): _sha256(path)
               for path in old_root.rglob('*') if path.is_file()
               and '__pycache__' not in path.relative_to(old_root).parts
               and 'slice-work' not in path.relative_to(old_root).parts}
    if archive.is_file():
        current[archive.name] = _sha256(archive)
    issues = []
    issues.extend(f'added: {name}' for name in sorted(current.keys() - expected.keys()))
    issues.extend(f'removed: {name}' for name in sorted(expected.keys() - current.keys()))
    issues.extend(f'changed: {name}' for name in sorted(expected.keys() & current.keys())
                  if expected[name] != current[name])
    if issues:
        raise ValueError('Historical legacy preservation failed: ' + '; '.join(issues))
    return {'status': 'UNCHANGED', 'files_checked': len(expected),
            'baseline': str(preserved_file), 'sha256': _sha256(preserved_file),
            'exclusions': ['__pycache__', 'slice-work']}


def _snapshot_root(path):
    path = Path(path).resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    entries = {}
    if path.is_file():
        entries['.'] = {'type': 'file', 'sha256': _sha256(path)}
        kind = 'file'
    else:
        kind = 'directory'
        for item in sorted(path.rglob('*')):
            relative = item.relative_to(path).as_posix()
            if item.is_symlink():
                entries[relative] = {'type': 'symlink', 'target': os.readlink(item)}
            elif item.is_file():
                entries[relative] = {'type': 'file', 'sha256': _sha256(item)}
            elif item.is_dir():
                entries[relative] = {'type': 'directory'}
    return {'path': str(path), 'kind': kind, 'entries': entries}


def snapshot_paths(paths):
    """Hash every file, including hidden files and caches; retain directory/link identity."""
    resolved = [Path(path).resolve() for path in paths]
    if len(set(resolved)) != len(resolved):
        raise ValueError('Duplicate preservation roots')
    return {'schema_version': 1, 'roots': [_snapshot_root(path) for path in resolved]}


def verify_preserved(snapshot):
    """Reject added, removed, changed or replaced legacy files; never refresh baseline."""
    problems = []
    historical = snapshot.get('historical_baseline')
    if historical and _sha256(historical['path']) != historical['sha256']:
        problems.append('changed historical preservation baseline')
    files = 0
    for before in snapshot['roots']:
        files += sum(item['type'] == 'file' for item in before['entries'].values())
        try:
            after = _snapshot_root(before['path'])
        except FileNotFoundError:
            problems.append(f'removed preservation root: {before["path"]}')
            continue
        if before['kind'] != after['kind']:
            problems.append(f'changed root type: {before["path"]}')
        old, new = before['entries'], after['entries']
        for name in sorted(new.keys() - old.keys()):
            problems.append(f'added: {before["path"]}/{name}')
        for name in sorted(old.keys() - new.keys()):
            problems.append(f'removed: {before["path"]}/{name}')
        for name in sorted(old.keys() & new.keys()):
            if old[name] != new[name]:
                problems.append(f'changed: {before["path"]}/{name}')
    if problems:
        raise ValueError('Legacy preservation failed: ' + '; '.join(problems))
    return {'status': 'UNCHANGED', 'files_checked': files,
            'roots': [entry['path'] for entry in snapshot['roots']]}


def _load_slice_runner(helper_path):
    # Compile the existing helper directly, avoiding new bytecode in the legacy tree.
    helper_path = Path(helper_path)
    namespace = {'__name__': 'corrected_batch_slicing_support', '__file__': str(helper_path)}
    exec(compile(helper_path.read_bytes(), str(helper_path), 'exec'), namespace)
    return namespace['run_slice']


def _verify_plan_sources(plan):
    for source in plan['sources']:
        if _sha256(source['manifest']) != source['sha256']:
            raise ValueError('Source manifest changed during batch preparation')
    for plate in plan['plates']:
        for part in plate['parts']:
            if _sha256(part['stl_path']) != part['sha256']:
                raise ValueError(f'STL SHA256 changed during batch: {part["id"]}')


def prepare_batch(new_manifest=None, old_manifest=None, *, execute=False, slice_runner=None):
    """Plan by default; execute=True calls the unchanged X2D helper once per color.

    Results stay in cloud-addition-v1/slice-work/corrected. The old tree and old
    ZIP must match the first stored baseline on every invocation, even after failure.
    slice_runner is dependency injection for offline tests, not an alternate CLI.
    """
    new_manifest = Path(new_manifest or ROOT / 'output/manifest.json').resolve()
    old_manifest = Path(old_manifest or ROOT.parent / 'production-v1/output/manifest.json').resolve()
    new_root, old_root = new_manifest.parent.parent, old_manifest.parent.parent
    if old_root != new_root.parent / 'production-v1':
        raise ValueError('Previous manifest must be in the sibling production-v1 project')
    if new_root == old_root or new_root.is_relative_to(old_root):
        raise ValueError('New batch work must be outside the previous production tree')
    archive = old_root.parent / 'claude-codex-48mm.zip'
    historical_file = new_root / 'preserved-files.json'
    historical = verify_preserved_files(historical_file)
    work = new_root / 'slice-work/corrected'
    work.mkdir(parents=True, exist_ok=True, mode=0o700)
    work.chmod(0o700)
    baseline_file = work / 'preservation-before.json'
    if baseline_file.exists():
        baseline = json.loads(baseline_file.read_text())
        if {root['path'] for root in baseline['roots']} != {str(old_root), str(archive)}:
            raise ValueError('Preservation baseline belongs to different source roots')
    else:
        baseline = snapshot_paths([old_root, archive])
        baseline['historical_baseline'] = {'path': str(historical_file), 'sha256': historical['sha256']}
        _private_json(baseline_file, baseline, exclusive=True)
    report = {'status': 'PREPARING', 'physical_print': 'NOT_RUN', 'device_sent': False,
              'physical_slot_binding': 'NOT_SET', 'work_dir': str(work), 'plate_results': [],
              'historical_preservation': historical}
    error = None
    try:
        verify_preserved(baseline)
        plan = build_batch_plan(new_manifest, old_manifest)
        _private_json(work / 'batch-plan.json', plan)
        report.update(design_ids=plan['design_ids'], part_count=plan['part_count'])
        if execute:
            for plate in plan['plates']:
                if (work / plate['output_name']).exists():
                    raise FileExistsError(work / plate['output_name'])
            runner = slice_runner or _load_slice_runner(old_root / 'slicing_support.py')
            for plate in plan['plates']:
                _verify_plan_sources(plan)
                result = runner([Path(part['stl_path']) for part in plate['parts']],
                                work / plate['output_name'], plate['color_key'], support=plate['support'])
                report['plate_results'].append({'color_key': plate['color_key'],
                                               'part_ids': [part['id'] for part in plate['parts']],
                                               'support': plate['support'], 'result': result})
                _private_json(work / 'batch-status.json', report)
            _verify_plan_sources(plan)
            report['status'] = 'OFFLINE_SLICED'
            report['estimated_total_seconds'] = sum(row['result']['estimated_seconds'] for row in report['plate_results'])
            report['estimated_total_filament_g'] = sum(row['result']['estimated_filament_g'] for row in report['plate_results'])
        else:
            report['status'] = 'PLANNED'
    except Exception as exc:
        error = exc
        report.update(status='FAILED', error=f'{type(exc).__name__}: {exc}')
    try:
        report['preservation'] = verify_preserved(baseline)
    except Exception as exc:
        report.update(status='FAILED', preservation_error=f'{type(exc).__name__}: {exc}')
        error = exc
    _private_json(work / 'batch-status.json', report)
    if error is not None:
        raise error
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--new-manifest', type=Path, default=ROOT / 'output/manifest.json')
    parser.add_argument('--old-manifest', type=Path, default=ROOT.parent / 'production-v1/output/manifest.json')
    parser.add_argument('--slice', action='store_true', help='Run offline slicing after validating; never send to a printer')
    args = parser.parse_args()
    print(json.dumps(prepare_batch(args.new_manifest, args.old_manifest, execute=args.slice), indent=2))
