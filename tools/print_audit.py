#!/usr/bin/env python3
"""Detect multi-color / prime-tower waste in Bambu Studio G-code.

Standard-library-only CLI that parses a sliced print (either a bare
``.gcode`` file or a ``.gcode.3mf`` / ``.3mf`` archive containing one) and
reports, per layer and per material, how much filament was actually
extruded on the body ("model"), supports, prime tower, brim/skirt and
"Custom" (priming / macro / scaffold) G-code sections. It is meant to make
color-change waste - e.g. building prime-tower mass on layers where no
real color change was needed, or printing unnecessary multi-color surface
layers - machine-checkable instead of something a human has to notice by
eye in a slice preview.

This tool only reads G-code comments and motion commands that Bambu
Studio emits (``; CHANGE_LAYER``, ``; Z_HEIGHT:``, ``; FEATURE:``,
``T<n>``, ``M82``/``M83``, ``G90``/``G91``, ``G92``, ``G0``/``G1``/``G2``/
``G3``). It does not parse the mesh, does not talk to a printer, and does
not open a GUI. Extrusion-derived masses are an estimate from
E-axis motion and nominal filament diameter/density; they are *not* a
substitute for the slicer's own total, because retraction/recovery and
machine purge routines are not fully captured by positive XY+E motion
alone. Where that matters this tool reports the slicer-declared total and
the residual separately rather than claiming exact consumption.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

PARAM = re.compile(r'([XYZEIJF])([-+]?(?:\d*\.\d+|\d+\.?\d*))')
TOOL_RE = re.compile(r'^T(\d+)\b')
SENTINEL_THRESHOLD = 1000  # Bambu park/purge sentinels (e.g. T65279, T65535)

CATEGORIES = ('model', 'support', 'tower', 'brim', 'custom')

SCOPE = (
    'Offline, read-only analysis of a single sliced G-code file (or the '
    'plate G-code embedded in a .gcode.3mf/.3mf archive). No mesh '
    'inspection, no GUI, no printer/network communication.'
)

LIMITATIONS = [
    'Extrusion masses are computed from positive-E, real-XY (or arc with '
    'I/J) motion using nominal filament_diameter/filament_density; they '
    'exclude retraction/recovery moves (no XY motion) and are therefore a '
    'path-based estimate, not the exact grams consumed at the nozzle. Recovery '
    'combined with XY motion can also overcount; this is not a guaranteed lower bound.',
    'Machine purge/wipe routines invoked via custom macros (e.g. AMS '
    'filament-change gcode) are only visible to this tool to the extent '
    'they emit G0/G1/G2/G3 moves inside the parsed G-code; firmware-side '
    'purge volumes are not otherwise modeled.',
    'Filament identity is tracked from T<n> tool-select commands. IDs at '
    f'or above {SENTINEL_THRESHOLD}, or outside the declared filament '
    'count when known, are treated as park/purge sentinels and are not '
    'counted as color changes.',
    'G-code emitted while the active FEATURE is "Custom" (macros, purge '
    'lines, priming before the first layer) is tallied into its own '
    '"custom" category rather than folded into model/support/tower/brim, '
    'and is excluded from the print-color-change stream.',
    'When filament_density is unavailable (raw .gcode input with no '
    'embedded project_settings, or a filament id missing density data) '
    'the mass for that filament id is reported as null/"unresolved" '
    'rather than guessed.',
]


def classify_feature(feature: Optional[str]) -> str:
    if feature is None or feature == 'Custom':
        return 'custom'
    if feature.startswith('Support'):
        return 'support'
    if feature == 'Prime tower':
        return 'tower'
    if feature in ('Brim', 'Skirt'):
        return 'brim'
    return 'model'


def load_gcode(path: Path):
    """Return (gcode_text, project_settings_or_None, source_kind)."""
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            names = [n for n in archive.namelist()
                     if n.startswith('Metadata/') and n.endswith('.gcode')]
            if not names:
                raise ValueError(f'No Metadata/*.gcode entry found inside archive: {path}')
            if len(names) != 1:
                raise ValueError('Audit each plate separately; multi-plate input is ambiguous')
            name = sorted(names)[0]
            code = archive.read(name).decode('utf-8', errors='replace')
            settings = None
            if 'Metadata/project_settings.config' in archive.namelist():
                settings = json.loads(archive.read('Metadata/project_settings.config'))
            if settings is not None and 'Metadata/slice_info.config' in archive.namelist():
                info = ET.fromstring(archive.read('Metadata/slice_info.config'))
                materials = info.findall('plate/filament')
                if materials and all(f.get('group_id') is not None for f in materials):
                    # Sliced physical assignment is authoritative over an Auto project setting.
                    mapping = list(settings.get('filament_map', []))
                    for f in materials:
                        i = int(f.get('id'))-1
                        if i < len(mapping):
                            mapping[i] = str(int(f.get('group_id'))+1)
                    settings['filament_map'] = mapping
        return code, settings, f'zip:{name}'
    return path.read_text(encoding='utf-8', errors='replace'), None, 'raw-gcode'


def _new_layer():
    return {
        'z': None,
        'had_color_change': False,
        'colors_by_category': defaultdict(set),
        'length_mm_by_category_color': defaultdict(lambda: defaultdict(float)),
    }


def parse_gcode(code: str, filament_count: Optional[int] = None):
    """Walk the G-code once and aggregate extrusion by layer/category/color.

    Returns a dict of intermediate results consumed by build_report().
    """
    x = y = e = 0.0
    layer = 0
    feature = None
    relative_e = False
    relative_xy = False
    color = None
    last_stream_color = None

    layers = defaultdict(_new_layer)
    prep_length_mm_by_color = defaultdict(float)  # extrusion before layer 1 ("custom")
    tool_events = []  # {'layer', 'id', 'accepted'}
    change_events = []  # {'layer', 'from', 'to', 'category'}
    total_layers_seen = 0

    for raw in code.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith('; CHANGE_LAYER'):
            layer += 1
            total_layers_seen = layer
            continue
        if line.startswith('; Z_HEIGHT:'):
            if layer:
                layers[layer]['z'] = float(line.split(':', 1)[1])
            continue
        if line.startswith('; FEATURE:'):
            feature = line.split(':', 1)[1].strip()
            continue
        if line.startswith(';'):
            continue
        command = line.split(';', 1)[0].strip()
        if not command:
            continue

        tool_match = TOOL_RE.match(command)
        if tool_match:
            tid = int(tool_match.group(1))
            if filament_count is not None:
                accepted = 0 <= tid < filament_count
            else:
                accepted = tid < SENTINEL_THRESHOLD
            tool_events.append({'layer': layer, 'id': tid, 'accepted': accepted})
            if accepted:
                color = tid
            continue

        op = command.split()[0]
        if op in ('M82', 'M83'):
            relative_e = op == 'M83'
            continue
        if op in ('G90', 'G91'):
            relative_xy = op == 'G91'
            continue
        if op == 'G92':
            p = {k: float(v) for k, v in PARAM.findall(command)}
            if 'X' in p:
                x = p['X']
            if 'Y' in p:
                y = p['Y']
            if 'E' in p:
                e = p['E']
            continue
        if op in ('G0', 'G1', 'G2', 'G3'):
            p = {k: float(v) for k, v in PARAM.findall(command)}
            nx = x + p.get('X', 0) if relative_xy else p.get('X', x)
            ny = y + p.get('Y', 0) if relative_xy else p.get('Y', y)
            de = p.get('E', 0) if relative_e else (p.get('E', e) - e)
            if 'E' in p:
                e = e + de if relative_e else p['E']
            moved_xy = abs(nx - x) + abs(ny - y) > 1e-8
            # An arc (G2/G3) with an I/J offset is a real path even if its
            # endpoint coincides with its start (e.g. a full circle).
            is_arc_path = op in ('G2', 'G3') and ('I' in p or 'J' in p)
            real_path = moved_xy or is_arc_path
            if de > 1e-9 and real_path:
                category = classify_feature(feature)
                if layer:
                    entry = layers[layer]
                    entry['colors_by_category'][category].add(color)
                    entry['length_mm_by_category_color'][category][color] += de
                    if category != 'custom':
                        if last_stream_color is not None and color != last_stream_color:
                            change_events.append({
                                'layer': layer, 'from': last_stream_color,
                                'to': color, 'category': category,
                            })
                            entry['had_color_change'] = True
                        last_stream_color = color
                else:
                    prep_length_mm_by_color[color] += de
            x, y = nx, ny

    return {
        'layers': layers,
        'prep_length_mm_by_color': prep_length_mm_by_color,
        'tool_events': tool_events,
        'change_events': change_events,
        'layer_count': total_layers_seen,
    }


def grams(length_mm: float, diameter_mm: Optional[float], density_g_cm3: Optional[float]):
    if diameter_mm is None or density_g_cm3 is None:
        return None
    area_mm2 = math.pi * (diameter_mm / 2) ** 2
    return length_mm * area_mm2 * density_g_cm3 / 1000.0


def build_report(code: str, settings: Optional[dict], source_kind: str,
                  source_path: Path, base_color_id: int):
    filament_diameter = None
    filament_density = None
    filament_map = None
    if settings is not None:
        filament_diameter = [float(v) for v in settings.get('filament_diameter', [])] or None
        filament_density = [float(v) for v in settings.get('filament_density', [])] or None
        filament_map = settings.get('filament_map')
    filament_count = len(filament_diameter) if filament_diameter else None

    parsed = parse_gcode(code, filament_count=filament_count)
    layers = parsed['layers']
    layer_count_header_match = re.search(r'; total layer number: (\d+)', code)
    declared_layer_count = int(layer_count_header_match.group(1)) if layer_count_header_match else None
    layer_count = declared_layer_count if declared_layer_count is not None else parsed['layer_count']

    declared_total_by_id = None
    weight_match = re.search(r'; total filament weight \[g\]\s*:\s*([\d.,\s]+)', code)
    if weight_match:
        declared_total_by_id = [float(v) for v in weight_match.group(1).strip().split(',')]

    def density_for(color_id):
        if color_id is None or filament_density is None or color_id >= len(filament_density):
            return None
        return filament_density[color_id]

    def diameter_for(color_id):
        if color_id is None or filament_diameter is None or color_id >= len(filament_diameter):
            return None
        return filament_diameter[color_id]

    def color_key(color_id):
        return 'unknown' if color_id is None else str(color_id)

    unresolved_density_ids = set()

    extrusion_mm = {cat: defaultdict(float) for cat in CATEGORIES}
    extrusion_g = {cat: defaultdict(float) for cat in CATEGORIES}
    extrusion_g_unresolved = {cat: set() for cat in CATEGORIES}

    layers_out = {}
    multi_color_model_layers = []
    multi_color_any_layers = []
    first_non_base_model_layer = None
    first_non_base_any_layer = None
    tower_grams_no_change = 0.0
    tower_layers_no_change = 0

    for layer_no in sorted(layers):
        entry = layers[layer_no]
        colors_by_category = {cat: sorted(s, key=lambda c: (c is None, c))
                               for cat, s in entry['colors_by_category'].items()}
        grams_by_category_color = {}
        for cat, by_color in entry['length_mm_by_category_color'].items():
            grams_by_category_color[cat] = {}
            for color_id, mm in by_color.items():
                ckey = color_key(color_id)
                extrusion_mm[cat][ckey] += mm
                dens = density_for(color_id)
                diam = diameter_for(color_id)
                g = grams(mm, diam, dens)
                grams_by_category_color[cat][ckey] = g
                if g is None:
                    unresolved_density_ids.add(ckey)
                    extrusion_g_unresolved[cat].add(ckey)
                else:
                    extrusion_g[cat][ckey] += g

        model_colors = set(colors_by_category.get('model', []))
        any_colors = set().union(*colors_by_category.values()) if colors_by_category else set()
        if len(model_colors) > 1:
            multi_color_model_layers.append(layer_no)
        if len(any_colors) > 1:
            multi_color_any_layers.append(layer_no)
        if model_colors - {base_color_id} and first_non_base_model_layer is None:
            first_non_base_model_layer = layer_no
        if any_colors - {base_color_id} and first_non_base_any_layer is None:
            first_non_base_any_layer = layer_no

        tower_by_color = entry['length_mm_by_category_color'].get('tower', {})
        tower_mm_total = sum(tower_by_color.values())
        tower_g_total = sum(
            g for g in (grams(mm, diameter_for(c), density_for(c)) for c, mm in tower_by_color.items())
            if g is not None
        )
        if tower_mm_total > 0 and not entry['had_color_change']:
            tower_layers_no_change += 1
            tower_grams_no_change += tower_g_total

        layers_out[layer_no] = {
            'z_mm': entry['z'],
            'colors_by_category': colors_by_category,
            'extrusion_mm_by_category_color': {
                cat: {color_key(c): mm for c, mm in by.items()}
                for cat, by in entry['length_mm_by_category_color'].items()
            },
            'extrusion_grams_by_category_color': grams_by_category_color,
            'had_color_change': entry['had_color_change'],
            'tower_grams_this_layer': tower_g_total,
        }

    tower_grams_before_first_non_base = None
    tower_layers_before_first_non_base = None
    if first_non_base_model_layer is not None:
        before = [n for n in layers_out if n < first_non_base_model_layer]
        tower_grams_before_first_non_base = sum(
            layers_out[n]['tower_grams_this_layer'] for n in before
        )
        tower_layers_before_first_non_base = sum(
            1 for n in before if layers_out[n]['tower_grams_this_layer'] > 0
        )

    # Preparation ("custom") extrusion before the first CHANGE_LAYER.
    prep_mm_by_color = {color_key(c): mm for c, mm in parsed['prep_length_mm_by_color'].items()}

    tool_events = parsed['tool_events']
    accepted_events = [t for t in tool_events if t['accepted']]
    sentinel_or_rejected = defaultdict(int)
    for t in tool_events:
        if not t['accepted']:
            sentinel_or_rejected[str(t['id'])] += 1

    def nozzle_for(color_id):
        if filament_map is None or color_id is None or color_id >= len(filament_map):
            return None
        return filament_map[color_id]

    change_events = []
    nozzle_loaded = {}
    nozzle_replacements = []
    for ev in parsed['change_events']:
        nf, nt = nozzle_for(ev['from']), nozzle_for(ev['to'])
        if nf is not None:
            nozzle_loaded.setdefault(nf, ev['from'])
        replaced = nt in nozzle_loaded and nozzle_loaded[nt] != ev['to'] if nt is not None else None
        if replaced:
            nozzle_replacements.append({'layer': ev['layer'], 'nozzle': nt,
                                        'from': nozzle_loaded[nt], 'to': ev['to']})
        if nt is not None:
            nozzle_loaded[nt] = ev['to']
        change_events.append({
            **ev,
            'same_nozzle': (nf == nt) if (nf is not None and nt is not None) else None,
            'requires_filament_replacement': replaced,
        })

    total_computed_grams = sum(
        sum(v for v in by.values())
        for by in extrusion_g.values()
    )
    total_declared_grams = sum(declared_total_by_id) if declared_total_by_id else None
    residual = (total_declared_grams - total_computed_grams) if total_declared_grams is not None else None

    source_bytes = source_path.read_bytes()
    report = {
        'status': 'OK',
        'source_path': str(source_path),
        'source_sha256': hashlib.sha256(source_bytes).hexdigest(),
        'source_kind': source_kind,
        'base_color_id': base_color_id,
        'layer_count': layer_count,
        'filament_count': filament_count,
        'filament_diameter_mm': filament_diameter,
        'filament_density_g_cm3': filament_density,
        'filament_map_nozzle': filament_map,
        'declared_total_grams_by_filament_id': declared_total_by_id,
        'declared_total_grams_source': (
            "G-code header comment '; total filament weight [g]'" if declared_total_by_id else None
        ),
        'tool_change_commands_total': len(tool_events),
        'tool_change_commands_accepted_as_color': len(accepted_events),
        'tool_change_commands_sentinel_or_out_of_range': dict(sentinel_or_rejected),
        'print_color_change_event_count': len(change_events),
        'nozzle_filament_replacement_count': len(nozzle_replacements) if filament_map else None,
        'nozzle_filament_replacements': nozzle_replacements,
        'color_change_events': change_events,
        'categories': list(CATEGORIES),
        'extrusion_mm_by_category_color': {
            cat: dict(by) for cat, by in extrusion_mm.items()
        },
        'extrusion_grams_by_category_color': {
            cat: dict(by) for cat, by in extrusion_g.items()
        },
        'unresolved_density_filament_ids': sorted(unresolved_density_ids),
        'preparation_extrusion_mm_by_color': prep_mm_by_color,
        'layers': layers_out,
        'first_non_base_color_model_layer': first_non_base_model_layer,
        'first_non_base_color_any_category_layer': first_non_base_any_layer,
        'multi_color_model_layers': multi_color_model_layers,
        'multi_color_model_layer_count': len(multi_color_model_layers),
        'multi_color_any_category_layers': multi_color_any_layers,
        'multi_color_any_category_layer_count': len(multi_color_any_layers),
        'tower_grams_before_first_non_base_color_model_layer': tower_grams_before_first_non_base,
        'tower_layer_count_before_first_non_base_color_model_layer': tower_layers_before_first_non_base,
        'tower_grams_on_layers_without_color_change': tower_grams_no_change,
        'tower_layer_count_without_color_change': tower_layers_no_change,
        'total_declared_grams': total_declared_grams,
        'total_computed_grams_conservative': total_computed_grams,
        'residual_declared_minus_computed_grams': residual,
        'scope': SCOPE,
        'limitations': LIMITATIONS,
    }
    return report


def waste_check(report, max_no_change_tower_g):
    """Enforce the explicitly selected budget; this is not print-quality approval."""
    reasons = []
    if report['layer_count'] <= 0:
        reasons.append('No printable layers were recognized')
    if report['unresolved_density_filament_ids']:
        reasons.append('Material mass is unresolved; zero waste cannot be inferred')
    value = report['tower_grams_on_layers_without_color_change']
    if value > max_no_change_tower_g + 1e-9:
        reasons.append(f'No-change tower mass {value:.3f} g exceeds {max_no_change_tower_g:.3f} g')
    return dict(passed=not reasons, reasons=reasons,
                max_no_change_tower_g=max_no_change_tower_g,
                scope='Waste budget only. Critical geometry, collision and physical quality are separate.')


def audit(path, base_color_id=0):
    path = Path(path)
    code, settings, source_kind = load_gcode(path)
    return build_report(code, settings, source_kind, path, base_color_id)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('input', help='Path to a .gcode, .gcode.3mf or .3mf file')
    parser.add_argument('--base-color-id', type=int, default=0,
                         help='Filament id (0-based) treated as the base/dominant color (default: 0)')
    parser.add_argument('--output', help='Write the full JSON report to this path')
    parser.add_argument('--max-no-change-tower-g', type=float,
                        help='Fail (exit 2) if non-changing layers exceed this tower budget, or mass is unresolved')
    args = parser.parse_args(argv)

    report = audit(args.input, base_color_id=args.base_color_id)
    if args.max_no_change_tower_g is not None:
        if args.max_no_change_tower_g < 0:
            parser.error('Tower budget cannot be negative')
        report['waste_check'] = waste_check(report, args.max_no_change_tower_g)
    text = json.dumps(report, indent=2, sort_keys=False)
    if args.output:
        Path(args.output).write_text(text + '\n')
    summary = {k: report[k] for k in [
        'status', 'layer_count', 'print_color_change_event_count',
        'nozzle_filament_replacement_count',
        'first_non_base_color_model_layer',
        'tower_grams_before_first_non_base_color_model_layer',
        'tower_layer_count_before_first_non_base_color_model_layer',
        'tower_grams_on_layers_without_color_change',
        'tower_layer_count_without_color_change',
        'multi_color_model_layer_count',
        'total_declared_grams', 'total_computed_grams_conservative',
        'residual_declared_minus_computed_grams',
    ]}
    if 'waste_check' in report:
        summary['waste_check'] = report['waste_check']
    print(json.dumps(summary, indent=2))
    return 2 if 'waste_check' in report and not report['waste_check']['passed'] else 0


if __name__ == '__main__':
    sys.exit(main())
