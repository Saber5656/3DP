"""Compare hanging pitch using model-only deposition, with explicit assumptions."""
import hashlib
import json
import math
from pathlib import Path
import re
import zipfile
import numpy as np

PARAM = re.compile(r'([XYZEIJ])([-+]?(?:\d*\.\d+|\d+\.?\d*))')


def deposited_centroid(code):
    x = y = z = e = height = 0.
    relative_e = relative_xy = started = False
    feature = 'Custom'
    moment = np.zeros(3)
    total = 0.
    for line in code.splitlines():
        if line.startswith('; CHANGE_LAYER'):
            started = True
        elif line.startswith('; Z_HEIGHT:'):
            z = float(line.split(':')[1])
        elif line.startswith('; LAYER_HEIGHT:'):
            height = float(line.split(':')[1])
        elif line.startswith('; FEATURE:'):
            feature = line.split(':',1)[1].strip()
        command = line.split(';',1)[0].strip()
        if not command:
            continue
        op = command.split()[0]
        p = {k:float(v) for k,v in PARAM.findall(command)}
        if op in {'M82','M83'}:
            relative_e = op == 'M83'
        elif op in {'G90','G91'}:
            relative_xy = op == 'G91'
        elif op == 'G92':
            x,y,e = p.get('X',x),p.get('Y',y),p.get('E',e)
        elif op in {'G0','G1','G2','G3'}:
            nx = x+p.get('X',0) if relative_xy else p.get('X',x)
            ny = y+p.get('Y',0) if relative_xy else p.get('Y',y)
            de = p.get('E',0) if relative_e else p.get('E',e)-e
            if 'E' in p:
                e += de
            is_model = feature not in {'Custom','Prime tower','Brim','Skirt'} and not feature.startswith('Support')
            if started and de > 0 and is_model:
                points = np.asarray([[x,y],[nx,ny]])
                if op in {'G2','G3'} and ('I' in p or 'J' in p):
                    cx,cy = x+p.get('I',0),y+p.get('J',0)
                    a0,a1 = math.atan2(y-cy,x-cx),math.atan2(ny-cy,nx-cx)
                    span = (a1-a0)%(2*math.pi) if op=='G3' else -((a0-a1)%(2*math.pi))
                    if abs(span)<1e-10:
                        span = 2*math.pi if op=='G3' else -2*math.pi
                    radius = math.hypot(x-cx,y-cy)
                    angles = np.linspace(a0,a0+span,max(3,math.ceil(abs(span)*radius/.10)+1))
                    points = np.column_stack([cx+radius*np.cos(angles),cy+radius*np.sin(angles)])
                lengths = np.linalg.norm(np.diff(points,axis=0),axis=1)
                distance = lengths.sum()
                if distance > 1e-8:
                    xy = np.sum((points[:-1]+points[1:])/2*lengths[:,None],axis=0)/distance
                    moment += de*np.r_[xy,z-height/2]
                    total += de
            x,y = nx,ny
    if total <= 0:
        raise ValueError('No model deposition found')
    return {'centroid_print_xyz_mm':(moment/total).tolist(), 'filament_length_mm':total}


def slice_centroid(path, rear_max):
    with zipfile.ZipFile(path) as archive:
        code = archive.read('Metadata/plate_1.gcode')
    result = deposited_centroid(code.decode())
    # slice.py preserves orientation/arrangement and translates every part by
    # [128, 110, 0]. The rear-most surface defines print Z=0 after -90 deg X.
    x,y,z = result['centroid_print_xyz_mm']
    result['centroid_upright_xyz_mm'] = [x-128,rear_max-z,y-110]
    result['gcode_sha256'] = hashlib.sha256(code).hexdigest()
    return result


def pitch(center, centroid):
    return math.degrees(math.atan2(center[1]-centroid[1],center[2]-centroid[2]))


def metrics(center, centroid):
    cases = [pitch([center[0],center[1]+dy,center[2]+dz],centroid)
             for dy in [-1,1] for dz in [-1,1]]
    return {'pitch_center_proxy_deg':pitch(center,centroid),
            'contact_sensitivity_plus_minus_1mm_yz_deg':[min(cases),max(cases)],
            'lateral_center_offset_mm':center[0]-centroid[0]}


def main():
    from build import ROOT, build_model, as_mesh
    reference = json.loads((ROOT/'source/previous-v4-balance.json').read_text())
    model = build_model()
    cm = slice_centroid(ROOT/'slicing/524-PROVISIONAL-DO-NOT-SEND.3mf',model['full'].bounding_box()[4])
    center = list(model['eyelet_center'])
    result = {'status':'ESTIMATE_NOT_PHYSICAL_TEST',
              'assumptions':['All four PLA colors have equal density and filament diameter.',
                             'Only object deposition is retained; supports, tower and purge are excluded.',
                             'The ring centre is a representative suspension point; the clasp contact is unknown.',
                             '+/-1 mm contact cases are illustrative sensitivity cases, not measured bounds.',
                             'Pitch is a Y-Z plane comparison; friction, constrained clasp motion and roll are not simulated.'],
              'previous_v4':reference,
              'current_v5':dict(cm,eyelet_center=center,
                                uniform_solid_centroid=as_mesh(model['full']).center_mass.tolist(),
                                **metrics(center,cm['centroid_upright_xyz_mm']))}
    result['pitch_reduction_deg'] = reference['pitch_center_proxy_deg']-result['current_v5']['pitch_center_proxy_deg']
    assert result['pitch_reduction_deg'] > 20, 'Hanging pitch improvement is too small'
    assert abs(result['current_v5']['pitch_center_proxy_deg']) < 2
    (ROOT/'output/balance-report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
