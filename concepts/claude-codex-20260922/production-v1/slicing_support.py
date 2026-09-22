"""Offline, single-material X2D slicing. Never connects to or sends to a printer.

Installed official presets are flattened into private, per-run settings. Source
STLs must already have the desired orientation and their lowest point at z=0.
Automatic face orientation is disabled. Arrangement may rotate about Z while
preserving the selected face on the bed.
"""
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
from xml.etree import ElementTree as ET
import zipfile

MACHINE_NAME = 'Bambu Lab X2D 0.4 nozzle'
PROCESS_NAME = '0.16mm Standard @BBL X2D'
BASIC = 'Bambu PLA Basic @BBL X2D 0.4 nozzle'
TRANSLUCENT = 'Bambu PLA Translucent @BBL X2D 0.4 nozzle'
COLORS = {
    'white': {'preset': BASIC, 'hex': '#FFFFFF', 'material': 'PLA Basic Jade White'},
    'black': {'preset': BASIC, 'hex': '#000000', 'material': 'PLA Basic Black'},
    'orange': {'preset': BASIC, 'hex': '#FF6A13', 'material': 'PLA Basic Orange'},
    'translucent_blue': {'preset': TRANSLUCENT, 'hex': '#0050B3', 'material': 'PLA Translucent Blue'},
    'gray': {'preset': BASIC, 'hex': '#8E9089', 'material': 'PLA Basic Gray'},
}
SETTINGS_ENTRY = 'Metadata/project_settings.config'
GCODE_ENTRY = 'Metadata/plate_1.gcode'
_NUMBER = r'[-+]?(?:\d*\.\d+|\d+\.?\d*)'
_PARAM = re.compile(r'([XYZEIJ])(' + _NUMBER + r')')


def find_preset_root(preset_root=None):
    """Locate installed official BBL profiles, without changing the installation."""
    explicit = preset_root or os.environ.get('BAMBU_PRESET_ROOT')
    candidates = [Path(explicit).expanduser()] if explicit else [
        Path.home() / 'Library/Application Support/BambuStudio/system/BBL',
        Path('/Applications/BambuStudio.app/Contents/Resources/profiles/BBL'),
    ]
    for root in candidates:
        if (root / 'machine' / f'{MACHINE_NAME}.json').is_file():
            return root.resolve()
    raise FileNotFoundError('Installed X2D presets not found; set BAMBU_PRESET_ROOT to system/BBL')


def resolve_preset(folder, name, stack=()):
    if name in stack:
        raise ValueError(f'Preset inheritance cycle: {name}')
    folder = Path(folder)
    path = folder / (name + '.json')
    if path.resolve().parent != folder.resolve():
        raise ValueError('Preset name must be local to its preset folder')
    source = json.loads(path.read_text())
    result = {}
    if source.get('inherits'):
        result.update(resolve_preset(folder, source['inherits'], (*stack, name)))
    for include in source.get('include', []):
        result.update(resolve_preset(folder, include, (*stack, name)))
    result.update({key: value for key, value in source.items() if key not in {'inherits', 'include'}})
    return result


def _private_json(path, value):
    path = Path(path)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
    path.chmod(0o600)


def prepare_settings(directory, color_key, support=False, *, preset_root=None):
    """Return paths and GUI delta metadata for one color, with no AMS slot binding."""
    if color_key not in COLORS:
        raise ValueError(f'Unknown color_key {color_key!r}; choose {tuple(COLORS)}')
    root = find_preset_root(preset_root)
    color = COLORS[color_key]
    machine = resolve_preset(root / 'machine', MACHINE_NAME)
    process = resolve_preset(root / 'process', PROCESS_NAME)
    filament = resolve_preset(root / 'filament', color['preset'])
    _validate_machine_material(machine, filament)
    overrides = dict(
        layer_height='0.16', curr_bed_type='Textured PEI Plate', wall_loops='3',
        sparse_infill_density='15%', sparse_infill_pattern='gyroid',
        print_sequence='by layer', enable_prime_tower='0', enable_support='1' if support else '0',
        support_type='tree(auto)', support_on_build_plate_only='1',
        support_filament='0', support_interface_filament='0',
        brim_type='outer_only', brim_width='3', brim_object_gap='0.1',
        initial_layer_speed=['30'] * 6, outer_wall_speed=['60'] * 6,
    )
    deltas = [';'.join(key for key, value in overrides.items() if process.get(key) != value),
              'filament_colour', '']
    process.update(overrides)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    result = {'deltas': deltas, 'preset_root': root, 'color_key': color_key,
              'expected_process': overrides}
    for kind, data, base, title in [
        ('machine', machine, MACHINE_NAME, 'Collectibles X2D 0.4'),
        ('process', process, PROCESS_NAME, f'Collectibles 0.16mm {color_key} support {int(support)}'),
        ('filament', filament, color['preset'], f'Collectibles {color["material"]}'),
    ]:
        data.update(name=title, inherits=base, **{'from': 'User'})
        if kind == 'filament':
            data['filament_colour'] = [color['hex']]
        path = directory / f'{kind}.json'
        _private_json(path, data)
        result[kind] = path
    return result


def _validate_machine_material(machine, filament):
    if machine.get('printer_model') != 'Bambu Lab X2D':
        raise ValueError('The archive/preset must use Bambu Lab X2D')
    nozzle = machine.get('nozzle_diameter', [])
    if not nozzle or any(float(item) != 0.4 for item in nozzle):
        raise ValueError('Expected X2D 0.4 mm nozzle settings')
    for key in ('machine_start_gcode', 'machine_end_gcode'):
        template = machine.get(key, '')
        if len(template) < 1000 or 'X2D' not in template:
            raise ValueError(f'Missing complete X2D {key}')
    density = filament.get('filament_density', [])
    if len(density) != 1 or not math.isfinite(float(density[0])) or float(density[0]) <= 0:
        raise ValueError('Expected positive single-material filament density')


def build_slice_command(stl_paths, output_3mf, settings, data_dir, bambu_bin):
    """Construct argv only. Logical filament 1 is not physical AMS slot 1."""
    paths = [str(Path(path)) for path in stl_paths]
    return [str(bambu_bin), '--debug', '2', '--datadir', str(data_dir),
            '--load-settings', f'{settings["machine"]};{settings["process"]}',
            '--load-filaments', str(settings['filament']),
            '--load-filament-ids', ','.join('1' for _ in paths),
            '--curr-bed-type', 'Textured PEI Plate', '--ensure-on-bed',
            '--arrange', '1', '--orient', '0', '--slice', '0',
            '--export-3mf', str(output_3mf), *paths]


def summarize_gcode(code):
    """Count actual extrusion moves by layer/feature; not a firmware simulator.

    G2/G3 count as one extrusion command. No arc length or maximum-gap claim is
    made. Travel, retraction, E-only priming and Custom start/end macros are excluded.
    """
    x = y = e = z = 0.0
    relative_e = relative_xy = False
    layer = 0
    feature = 'Custom'
    obj = None
    layers = []
    features = Counter()
    objects = {}
    arc_count = 0
    for line in code.splitlines():
        if line.startswith('; CHANGE_LAYER'):
            layer += 1
            feature = 'Custom'
            layers.append({'layer': layer, 'z_mm': z, 'extrusion_moves': 0, 'support_extrusion_moves': 0})
        elif line.startswith('; Z_HEIGHT:'):
            z = float(line.split(':', 1)[1])
            if layers:
                layers[-1]['z_mm'] = z
        elif line.startswith('; FEATURE:'):
            feature = line.split(':', 1)[1].strip()
        elif line.startswith('; OBJECT_ID:'):
            obj = line.split(':', 1)[1].strip()
        command = line.split(';', 1)[0].strip()
        if not command:
            continue
        op = command.split()[0]
        values = {key: float(value) for key, value in _PARAM.findall(command)}
        if op in {'M82', 'M83'}:
            relative_e = op == 'M83'
        elif op in {'G90', 'G91'}:
            relative_xy = op == 'G91'
        elif op == 'G92':
            x, y, e = values.get('X', x), values.get('Y', y), values.get('E', e)
        elif op in {'G0', 'G1', 'G2', 'G3'}:
            end_x = x + values.get('X', 0) if relative_xy else values.get('X', x)
            end_y = y + values.get('Y', 0) if relative_xy else values.get('Y', y)
            de = values.get('E', 0) if relative_e else values.get('E', e) - e
            if 'E' in values:
                e = e + de if relative_e else values['E']
            moved = abs(end_x - x) + abs(end_y - y) > 1e-9 or op in {'G2', 'G3'}
            if layer and feature != 'Custom' and de > 0 and moved:
                layers[-1]['extrusion_moves'] += 1
                features[feature] += 1
                is_support = 'support' in feature.lower()
                if is_support:
                    layers[-1]['support_extrusion_moves'] += 1
                if op in {'G2', 'G3'}:
                    arc_count += 1
                if obj is not None and not is_support and feature not in {'Brim', 'Skirt', 'Prime tower'}:
                    stats = objects.setdefault(obj, {'first_layer': layer, 'last_layer': layer, 'extrusion_moves': 0})
                    stats['last_layer'] = layer
                    stats['extrusion_moves'] += 1
            x, y = end_x, end_y
    return dict(layer_count=layer, extrusion_moves=sum(features.values()),
                arc_extrusion_moves=arc_count, support_extrusion_moves=sum(
                    value for key, value in features.items() if 'support' in key.lower()),
                features=dict(features), layers=layers, objects=objects,
                empty_layers=[item['layer'] for item in layers if not item['extrusion_moves']])


def extract_warnings(log):
    """Retain warnings verbatim, including unknown ones; do not suppress end macros."""
    return list(dict.fromkeys(line for line in log.splitlines()
                             if re.search(r'warning|\bwarn\b|\berror\b|invalid|influence area|floating|cantilever|unsupported', line, re.I)))


def inspect_3mf(path, *, cli_log='', expected_support=None):
    """Validate one sliced X2D plate and return actual estimates and extrusion counts."""
    path = Path(path)
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError('Corrupt 3MF archive')
        settings = json.loads(archive.read(SETTINGS_ENTRY))
        _validate_machine_material(settings, settings)
        for key in ('filament_colour', 'filament_settings_id'):
            if len(settings.get(key, [])) != 1:
                raise ValueError(f'Expected single-material plate ({key})')
        slices = ET.fromstring(archive.read('Metadata/slice_info.config'))
        plates = slices.findall('plate')
        gcodes = [name for name in archive.namelist() if re.fullmatch(r'Metadata/plate_\d+\.gcode', name)]
        if len(plates) != 1 or gcodes != [GCODE_ENTRY]:
            raise ValueError('Expected exactly one sliced plate; split large batches')
        plate = plates[0]
        meta = {entry.get('key'): entry.get('value') for entry in plate.findall('metadata')}
        filaments = [dict(entry.attrib) for entry in plate.findall('filament')]
        if len(filaments) != 1:
            raise ValueError('Expected one single-material filament record')
        if meta.get('outside') == 'true':
            raise ValueError('Slicer reports geometry outside the plate')
        code_bytes = archive.read(GCODE_ENTRY)
    code = code_bytes.decode('utf-8')
    paths = summarize_gcode(code)
    if not paths['layer_count'] or not paths['extrusion_moves']:
        raise ValueError('No actual layer extrusion found')
    if paths['empty_layers']:
        raise ValueError(f'Layers without extrusion: {paths["empty_layers"]}')
    declared = re.search(r'^; total layer number:\s*(\d+)', code, re.M)
    if declared and int(declared[1]) != paths['layer_count']:
        raise ValueError('G-code layer count disagrees with declared count')
    seconds = int(meta['prediction'])
    grams = float(meta['weight'])
    if seconds <= 0 or not math.isfinite(grams) or grams <= 0:
        raise ValueError('Missing positive time/weight estimate')
    support_used = meta.get('support_used') == 'true'
    if support_used != bool(paths['support_extrusion_moves']):
        raise ValueError('Support metadata disagrees with actual extrusion')
    if expected_support is False and support_used:
        raise ValueError('Unexpected support extrusion')
    warnings = extract_warnings(cli_log)
    for entry in slices.iter():
        if 'warning' in entry.tag.lower():
            warnings.append(ET.tostring(entry, encoding='unicode'))
    if expected_support is True and not support_used:
        warnings.append('Support requested, but slicer generated no support paths; inspect overhangs.')
    return dict(status='OFFLINE_SLICE_VALIDATED', printer_model=settings['printer_model'],
                nozzle_mm=settings['nozzle_diameter'], bed=settings.get('curr_bed_type'),
                filament_density_g_cm3=float(settings['filament_density'][0]),
                estimated_seconds=seconds, estimated_filament_g=grams, filaments=filaments,
                support_used=support_used, warnings=warnings,
                gcode_sha256=hashlib.sha256(code_bytes).hexdigest(),
                package_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                gui_roundtrip='NOT_RUN', physical_print='NOT_RUN',
                physical_slot_binding='NOT_SET',
                first_layer_time_metadata=meta.get('first_layer_time'),
                limitations=['Counts do not prove support removability, layer continuity, fit, strength or print success.',
                             'No live printer, current AMS allocation or clear-bed state was inspected.',
                             'Estimates are slicer values; start-macro purge and actual consumption are not guaranteed.'],
                **paths)


def patch_gui_deltas(path, deltas):
    """Preserve overrides on GUI import; change only project-settings metadata."""
    if len(deltas) != 3 or not all(isinstance(value, str) for value in deltas):
        raise ValueError('Single-material delta list must be process, filament, machine')
    path = Path(path)
    fd, temp_name = tempfile.mkstemp(prefix='.gui-deltas-', suffix='.3mf', dir=path.parent)
    os.close(fd)
    temp = Path(temp_name)
    try:
        with zipfile.ZipFile(path) as src, zipfile.ZipFile(temp, 'w') as dst:
            original_gcode = src.read(GCODE_ENTRY)
            for info in src.infolist():
                value = src.read(info.filename)
                if info.filename == SETTINGS_ENTRY:
                    settings = json.loads(value)
                    settings['different_settings_to_system'] = deltas
                    value = (json.dumps(settings, indent=2) + '\n').encode()
                dst.writestr(info, value)
            dst.comment = src.comment
        with zipfile.ZipFile(temp) as check:
            if check.testzip() is not None or check.read(GCODE_ENTRY) != original_gcode:
                raise ValueError('G-code changed while updating GUI delta metadata')
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _check_inputs(stl_paths):
    import numpy as np
    import trimesh
    paths = [Path(path).expanduser().resolve() for path in stl_paths]
    if not paths:
        raise ValueError('At least one pre-oriented STL is required')
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(path)
        if path.suffix.lower() != '.stl':
            raise ValueError('Only pre-oriented STL input is supported')
        mesh = trimesh.load_mesh(path)
        if not mesh.is_watertight or not np.isfinite(mesh.vertices).all():
            raise ValueError(f'STL must be finite and watertight: {path.name}')
        if abs(mesh.bounds[0, 2]) > 0.01:
            raise ValueError(f'STL must already sit at z=0: {path.name}')
        if any(mesh.extents[:2] > 250) or mesh.extents[2] > 261:
            raise ValueError(f'STL exceeds X2D build space with 3 mm brim: {path.name}')
    return paths


def run_slice(stl_paths, output_3mf, color_key, support=False, *, preset_root=None,
              bambu_bin=None, timeout=900):
    """Slice one color offline and return inspect_3mf report plus local evidence paths.

    Existing outputs are never overwritten. CLI failures/validation failures leave
    private evidence next to the requested output and do not publish output_3mf.
    """
    paths = _check_inputs(stl_paths)
    output = Path(output_3mf).expanduser().resolve()
    if output.suffix.lower() != '.3mf':
        raise ValueError('Output must have .3mf suffix')
    if output.exists():
        raise FileExistsError(output)
    binary = Path(bambu_bin or os.environ.get('BAMBU_STUDIO_BIN', '/Applications/BambuStudio.app/Contents/MacOS/BambuStudio'))
    if not binary.is_file():
        raise FileNotFoundError(binary)
    output.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=f'.{output.stem}-slicing-', dir=output.parent))
    settings = prepare_settings(work / 'settings', color_key, support, preset_root=preset_root)
    data_dir = work / 'profile'
    data_dir.mkdir(mode=0o700)
    candidate = work / 'candidate.3mf'
    command = build_slice_command(paths, candidate, settings, data_dir, binary)
    _private_json(work / 'invocation.json', {'argv': command, 'inputs': [
        {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()} for path in paths]})
    log_path = work / 'bambu-cli.log'
    with log_path.open('w') as log:
        log_path.chmod(0o600)
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=timeout, check=False)
    if result.returncode or not candidate.is_file():
        raise RuntimeError(f'Bambu CLI failed ({result.returncode}); evidence: {work}')
    patch_gui_deltas(candidate, settings['deltas'])
    report = inspect_3mf(candidate, cli_log=log_path.read_text(errors='replace'), expected_support=support)
    with zipfile.ZipFile(candidate) as archive:
        actual = json.loads(archive.read(SETTINGS_ENTRY))
    for key, expected in settings['expected_process'].items():
        if actual.get(key) != expected:
            raise ValueError(f'Sliced setting mismatch for {key}; evidence: {work}')
    if actual['filament_colour'] != [COLORS[color_key]['hex']]:
        raise ValueError(f'Sliced filament color mismatch; evidence: {work}')
    for key in ('machine_start_gcode', 'machine_end_gcode'):
        if actual[key] != json.loads(settings['machine'].read_text())[key]:
            raise ValueError(f'X2D official template changed: {key}; evidence: {work}')
    report.update(color_key=color_key, evidence_dir=str(work), cli_log=str(log_path),
                  output_3mf=str(output), gui_delta_metadata=settings['deltas'])
    _private_json(work / 'report.json', report)
    # Same filesystem: hard-link publication is atomic and cannot overwrite a race.
    os.link(candidate, output)
    candidate.unlink()
    return report


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stls', type=Path, nargs='+')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--color', choices=COLORS, required=True)
    parser.add_argument('--support', action='store_true')
    args = parser.parse_args()
    print(json.dumps(run_slice(args.stls, args.output, args.color, args.support), indent=2))
