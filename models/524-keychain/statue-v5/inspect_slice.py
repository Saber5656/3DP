"""Read-only check and layer plots from the generated provisional G-code."""
import argparse
from collections import Counter, defaultdict
import json
import math
import os
from pathlib import Path
import re
from xml.etree import ElementTree as ET
import zipfile
os.environ.setdefault('MPLCONFIGDIR', '/tmp/524-keychain-matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import numpy as np
from build import ROOT, COLORS, build_model

PARAM = re.compile(r'([XYZEIJ])([-+]?(?:\d*\.\d+|\d+\.?\d*))')


def verify_slice_warnings(lines):
    for line in lines:
        if 'prime tower is too close' in line.lower():
            raise ValueError('Prime Tower clearance warning remains: ' + line)


def crosses_vertical_passage(points, z, center_xy, axial_range):
    """Does a segment cross the 2 mm bore along print Z? Bead width excluded."""
    if not axial_range[0] <= z <= axial_range[1]:
        return False
    a,b = np.asarray(points, dtype=float)
    center = np.asarray(center_xy)
    delta = b-a
    t = np.clip(np.dot(center-a,delta)/np.dot(delta,delta), 0, 1) if np.dot(delta,delta)>1e-16 else 0.
    return bool(np.linalg.norm(a+t*delta-center) < 1.0)


def inspect(folder):
    folder = Path(folder)
    log_lines = (folder/'slice.log').read_text().splitlines()
    verify_slice_warnings(log_lines)
    path = folder / '524-PROVISIONAL-DO-NOT-SEND.3mf'
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        code = archive.read('Metadata/plate_1.gcode').decode()
        settings = json.loads(archive.read('Metadata/project_settings.config'))
        plate = ET.fromstring(archive.read('Metadata/slice_info.config')).find('plate')
        model_config = ET.fromstring(archive.read('Metadata/model_settings.config'))
        meta = {e.get('key'): e.get('value') for e in plate.findall('metadata')}
        materials = [dict(e.attrib) for e in plate.findall('filament')]
    assert meta['outside'] == 'false'
    assert settings['printer_model'] == 'Bambu Lab X2D'
    assert settings['filament_colour'] == list(COLORS.values())
    assert all(f['used_for_object'] == 'true' for f in materials)
    normal_count = len(model_config.findall("object/part[@subtype='normal_part']"))
    blocker_count = len(model_config.findall("object/part[@subtype='support_blocker']"))
    assert normal_count == 4 and blocker_count == 1
    x = y = z = e = 0.
    layer = 0
    color = 0
    relative_e = relative_xy = False
    feature = 'Custom'
    segments = []
    model_moves = Counter()
    lengths = defaultdict(float)
    layer_moves = Counter()
    toolchanges = 0
    path_bounds = {}
    for line in code.splitlines():
        if line.startswith('; CHANGE_LAYER'):
            layer += 1
        elif line.startswith('; Z_HEIGHT:'):
            z = float(line.split(':')[1])
        elif line.startswith('; FEATURE:'):
            feature = line.split(':', 1)[1].strip()
        command = line.split(';', 1)[0].strip()
        if not command:
            continue
        op = command.split()[0]
        p = {k: float(v) for k, v in PARAM.findall(command)}
        if op in {'T0', 'T1', 'T2', 'T3'}:
            color = int(op[1:])
            toolchanges += 1
        elif op in {'M82', 'M83'}:
            relative_e = op == 'M83'
        elif op in {'G90', 'G91'}:
            relative_xy = op == 'G91'
        elif op == 'G92':
            x, y, e = p.get('X', x), p.get('Y', y), p.get('E', e)
        elif op in {'G0', 'G1', 'G2', 'G3'}:
            nx = x + p.get('X', 0) if relative_xy else p.get('X', x)
            ny = y + p.get('Y', 0) if relative_xy else p.get('Y', y)
            de = p.get('E', 0) if relative_e else p.get('E', e) - e
            if 'E' in p:
                e += de
            if layer and de > 0 and (abs(nx-x)+abs(ny-y) > 1e-8 or op in {'G2', 'G3'}) and feature != 'Custom':
                category = 'support' if feature.startswith('Support') else ('tower' if feature == 'Prime tower' else ('brim' if feature in {'Brim','Skirt'} else 'model'))
                lengths[category] += de
                layer_moves[layer] += 1
                points = [(x, y), (nx, ny)]
                if op in {'G2','G3'} and ('I' in p or 'J' in p):
                    cx, cy = x+p.get('I',0), y+p.get('J',0)
                    a0 = math.atan2(y-cy, x-cx)
                    a1 = math.atan2(ny-cy, nx-cx)
                    span = (a1-a0) % (2*math.pi)
                    if op == 'G2':
                        span = -((a0-a1) % (2*math.pi))
                    if abs(span) < 1e-10:
                        span = -2*math.pi if op == 'G2' else 2*math.pi
                    radius = math.hypot(x-cx,y-cy)
                    angles = np.linspace(a0,a0+span,max(3, math.ceil(abs(span)*radius/.15)))
                    points = np.column_stack((cx+radius*np.cos(angles),cy+radius*np.sin(angles)))
                if category in {'model', 'support', 'tower'}:
                    name = 'tower' if category == 'tower' else 'object_and_support'
                    coords = np.asarray(points)
                    low, high = coords.min(axis=0), coords.max(axis=0)
                    if name in path_bounds:
                        low = np.minimum(low, path_bounds[name][0])
                        high = np.maximum(high, path_bounds[name][1])
                    path_bounds[name] = np.asarray([low, high])
                if category in {'model','support'}:
                    for a,b in zip(points,points[1:]):
                        segments.append((layer,z,color,category,[a,b]))
                if category == 'model':
                    model_moves[color] += 1
            x,y = nx,ny
    expected_layers = int(re.search(r'; total layer number: (\d+)', code).group(1))
    assert layer == expected_layers and layer > 0, layer
    assert all(model_moves[c] > 0 for c in range(4))
    assert not [i for i in range(1,layer+1) if not layer_moves[i]]
    nominal_grams = {k: v*math.pi*(1.75/2)**2*1.24/1000 for k,v in lengths.items()}
    total = float(meta['weight'])
    log_errors = [line for line in log_lines if '[error]' in line]
    obj, tower = path_bounds['object_and_support'], path_bounds['tower']
    xy_gap = np.maximum(np.maximum(obj[0]-tower[1], tower[0]-obj[1]), 0.)
    tower_gap = float(np.linalg.norm(xy_gap))
    assert tower_gap > 0, 'Tower and object/support extrusion bounds overlap'
    face_min_z = min(s[1] for s in segments if s[2] in (1, 2, 3) and s[3] == 'model')
    support_max_z = max((s[1] for s in segments if s[3] == 'support'), default=0.)
    assert support_max_z < face_min_z, 'Support reaches facial color height'
    # Check extrusion centre lines throughout a 2 mm cylindrical passage.
    # This is narrower than the CAD 2.4 mm gauge, and not a physical fit test.
    model = build_model()
    gx, gy, gz = model['eyelet_gauge_center']
    rear = max(s.bounding_box()[4] for s in model['parts'].values())
    gauge_xy = [128+gx, 110+gz]
    gauge_z = rear-gy
    hole_crossings = Counter()
    for l, z, c, category, points in segments:
        if crosses_vertical_passage(points, z, gauge_xy, [gauge_z-2.1,gauge_z+2.1]):
            hole_crossings[category] += 1
    assert not hole_crossings, f'Extrusion centre lines obstruct top passage: {dict(hole_crossings)}'
    report = dict(status='PASS',scope='offline provisional slice; no printer send',
                  production_readiness='NOT_READY',
                  slicer_log_error_count=len(log_errors),
                  unresolved_slicer_log_errors=log_errors,
                  runtime_compatibility='NOT_RUN',
                  normal_material_part_count=normal_count,support_blocker_count=blocker_count,
                  printer=settings['printer_model'],slicer='BambuStudio 02.08.02.61',
                  layer_height_mm=float(settings['layer_height']),layer_count=layer,
                  filament_map=settings['filament_map'],physical_AMS_slots='NOT_CONFIRMED',
                  estimated_time_seconds=int(meta['prediction']),estimated_total_grams=total,
                  material_estimates=materials,model_extrusion_moves=dict(model_moves),
                  nominal_extrusion_grams_by_feature=nominal_grams,
                  remaining_purge_and_custom_grams=total-sum(nominal_grams.values()),
                  feature_mass_note='Derived from E movement and nominal diameter/density; remaining mass is slicer total minus these features, not a separately reported purge mass.',
                  tool_selection_commands=toolchanges,empty_layers=[],outside=False,
                  physical_print='NOT_RUN',hardware_fit='NOT_RUN',
                  face_min_extrusion_z_mm=face_min_z,
                  support_max_extrusion_z_mm=support_max_z,
                  eyelet_inner_2mm_passage_moves=dict(hole_crossings),
                  prime_tower_clearance_warning=False,
                  extrusion_xy_bounds_mm={k: v.tolist() for k,v in path_bounds.items()},
                  tower_to_object_support_bbox_gap_mm=tower_gap,
                  clearance_note='Extrusion centreline bounding boxes only; excludes bead width, brim and toolhead sweep. The slicer proximity warning must also be absent.',
                  warnings=log_lines)
    color_layers = defaultdict(set)
    for l, z, c, category, points in segments:
        if category == 'model':
            color_layers[l].add(c)
    face_layers = sorted(l for l, colors in color_layers.items() if {1, 2, 3} <= colors)
    assert face_layers, 'No layer with all three facial colors'
    face_layer = face_layers[len(face_layers)//2]
    body_layer = layer//2
    fig,axes=plt.subplots(1,3,figsize=(13,5),facecolor='#f2f1ec')
    for ax,title,selected in zip(axes,['ALL MODEL LAYERS / top view',
                                     f'LAYER {body_layer} / body and support',
                                     f'LAYER {face_layer} / digits and mouth'],[None,body_layer,face_layer]):
        for layer_id in sorted({s[0] for s in segments}):
            if selected is not None and layer_id != selected:
                continue
            for category in ['support','model']:
                if selected is None and category == 'support':
                    continue
                for c,hex_color in enumerate(COLORS.values()):
                    lines=[s[4] for s in segments if s[0]==layer_id and s[2]==c and s[3]==category]
                    if lines:
                        ax.add_collection(LineCollection(lines,colors=hex_color if category=='model' else '#9ba2a8',linewidths=.65))
        ax.set(xlim=(103,154),ylim=(104,159),aspect='equal')
        ax.set_title(title,fontsize=10)
        ax.set_facecolor('#ece9df')
        ax.set_xlabel('X / mm')
        ax.set_ylabel('Y / mm')
    fig.suptitle('524 / ACTUAL PROVISIONAL TOOLPATHS',fontsize=19,weight='bold')
    fig.text(.07,.025,f"Generic PLA / 0.4 mm nozzle / {report['layer_height_mm']:.2f} mm layers / gray = supports / no physical print yet",fontsize=10)
    fig.tight_layout(rect=[0,.13,1,.91])
    fig.savefig(folder/'layers.png',dpi=150)
    plt.close(fig)
    report['face_colors_together_layers'] = face_layers
    (folder/'inspection.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['status','layer_count','estimated_time_seconds','estimated_total_grams','nominal_extrusion_grams_by_feature','remaining_purge_and_custom_grams']},indent=2))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--with-dots',action='store_true')
    args=parser.parse_args()
    inspect(ROOT/'slicing'/('with-dots' if args.with_dots else ''))
