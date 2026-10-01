"""Inspect actual physical-Z extrusion near the hook; never sends a print."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import zipfile
from xml.etree import ElementTree as ET

import numpy as np
from shapely.geometry import LineString, box
from shapely.ops import unary_union

PARAM = re.compile(r'([XYZEIJF])([-+]?(?:\d*\.\d+|\d+\.?\d*))')


def segments(code):
    xyz = np.zeros(3)
    e, layer, width, height, feed = 0., 0, .42, .08, 0.
    relative_e = relative_xyz = False
    feature = 'Custom'
    for line in code.splitlines():
        if line.startswith('; CHANGE_LAYER'):
            layer += 1
        for prefix, name in [('; FEATURE:','feature'), ('; LINE_WIDTH:','width'), ('; LAYER_HEIGHT:','height')]:
            if line.startswith(prefix):
                value = line.split(':',1)[1].strip()
                if name == 'feature': feature = value
                elif name == 'width': width = float(value)
                else: height = float(value)
        command = line.split(';',1)[0].strip()
        if not command: continue
        op = command.split()[0]
        p = {k:float(v) for k,v in PARAM.findall(command)}
        if op in {'M82','M83'}: relative_e = op == 'M83'
        elif op in {'G90','G91'}: relative_xyz = op == 'G91'
        elif op == 'G92':
            xyz = np.array([p.get(k,v) for k,v in zip('XYZ',xyz)])
            e = p.get('E',e)
        elif op in {'G0','G1','G2','G3'}:
            nxt = np.array([v+p.get(k,0) if relative_xyz else p.get(k,v) for k,v in zip('XYZ',xyz)])
            de = p.get('E',0) if relative_e else p.get('E',e)-e
            e += de
            feed = p.get('F',feed)
            arc = op in {'G2','G3'} and ('I' in p or 'J' in p)
            if layer and de > 1e-9 and (np.linalg.norm(nxt[:2]-xyz[:2]) > 1e-8 or arc) and feature != 'Custom':
                points = np.array([xyz,nxt])
                if arc:
                    center = xyz[:2]+[p.get('I',0),p.get('J',0)]
                    a0 = math.atan2(xyz[1]-center[1],xyz[0]-center[0])
                    a1 = math.atan2(nxt[1]-center[1],nxt[0]-center[0])
                    span = (a1-a0)%(2*math.pi) if op == 'G3' else -((a0-a1)%(2*math.pi))
                    if abs(span) < 1e-10: span = (1 if op == 'G3' else -1)*2*math.pi
                    radius = np.linalg.norm(xyz[:2]-center)
                    angles = np.linspace(a0,a0+span,max(3,math.ceil(abs(span)*radius/.05)))
                    points = np.column_stack([center[0]+radius*np.cos(angles),
                                              center[1]+radius*np.sin(angles),
                                              np.linspace(xyz[2],nxt[2],len(angles))])
                category = ('support' if feature.startswith('Support') else 'tower' if feature == 'Prime tower'
                            else 'brim' if feature in {'Brim','Skirt'} else 'model')
                yield dict(points=points, feature=feature, category=category, layer=layer,
                           width=width, height=height, speed_mm_s=feed/60)
            xyz = nxt


def inspect(path, y_origin=180):
    path = Path(path)
    with zipfile.ZipFile(path) as archive:
        code = archive.read('Metadata/plate_1.gcode').decode()
        info = ET.fromstring(archive.read('Metadata/slice_info.config'))
        settings = json.loads(archive.read('Metadata/project_settings.config'))
    moves = list(segments(code))
    center = np.array([128, y_origin+40.8, 85*40/153/2])
    # Above the 40 mm body tip only the loop exists. A wider ROI would pick
    # up the ear's earlier perimeter and mistake it for the loop's first layer.
    region = box(126.79,y_origin+40.01,129.21,y_origin+45)
    selected = []
    for move in moves:
        if move['category'] in {'model','support'}:
            pts = move['points']
            if pts[:,0].min() <= 131 and pts[:,0].max() >= 125 and pts[:,1].max() >= y_origin+36:
                selected.append(move)
    loop = [s for s in selected if s['category']=='model' and
            LineString(s['points'][:,:2]).intersects(region)]
    first_z = min(s['points'][:,2].min() for s in loop)
    first = [s for s in loop if np.allclose(s['points'][:,2],first_z,atol=1e-5)]
    footprint = unary_union([LineString(s['points'][:,:2]).buffer(s['width']/2) for s in first]).intersection(region)
    nearby_support = [s for s in selected if s['category']=='support' and
                      first_z-.25 <= s['points'][:,2].max() < first_z-.01]
    support_top = max((s['points'][:,2].max() for s in nearby_support),default=-1)
    support = unary_union([LineString(s['points'][:,:2]).buffer(s['width']/2) for s in nearby_support])
    coverage = footprint.intersection(support).area/footprint.area
    # 0.2 mm is half a 0.4 mm bead, used only as a separate conservative
    # coverage diagnostic. The raw directly-supported fraction remains visible.
    reachable = footprint.intersection(support.buffer(.2)).area/footprint.area
    min_radius = float('inf')
    for move in selected:
        for a,b in zip(move['points'],move['points'][1:]):
            # Only the portion inside the gauge's axial extent can obstruct it.
            if abs(b[0]-a[0]) < 1e-9:
                if abs(a[0]-center[0]) > 2.1: continue
                low,high=0.,1.
            else:
                low,high=sorted([(center[0]-2.1-a[0])/(b[0]-a[0]),(center[0]+2.1-a[0])/(b[0]-a[0])])
                low,high=max(low,0),min(high,1)
                if low>high: continue
            a1,b1=a+low*(b-a),a+high*(b-a)
            # Width/2 in every radial direction overestimates the thin layer's
            # vertical extent, so this deliberately errs toward a blocked bore.
            yz=np.array([a1[1:],b1[1:]])-center[1:]
            delta=yz[1]-yz[0]
            t=np.clip(-np.dot(yz[0],delta)/max(np.dot(delta,delta),1e-20),0,1)
            min_radius=min(min_radius,float(np.linalg.norm(yz[0]+t*delta)-move['width']/2))
    warnings=[dict(e.attrib) for e in info.findall('plate/warning')]
    critical=[w for w in warnings if w.get('msg')!='not_support_traditional_timelapse']
    report=dict(source=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                hook_first_extrusion_z_mm=float(first_z), nearest_support_z_mm=float(support_top),
                support_gap_toolpath_z_mm=float(first_z-support_top),
                direct_underside_support_fraction=coverage,
                underside_coverage_with_half_bead_reach=reachable,
                conservative_free_bore_radius_mm=min_radius,
                hook_perimeter_max_speed_mm_s=max(s['speed_mm_s'] for s in loop if 'wall' in s['feature'].lower()),
                no_sparse_layers=settings['wipe_tower_no_sparse_layers'], warnings=warnings,
                checks=dict(support_close=bool(first_z-support_top<=.241),
                            underside_covered=reachable>=.90, bore_clear=min_radius>=1.,
                            no_unresolved_slice_warning=not critical),
                physical_validation='NOT_RUN',
                limitations=['Coverage checks the first hook underside, not every later overhang.',
                             'The 45-degree bore roof is independently checked in CAD tests.',
                             'Bead envelope uses nominal width; cooling, sag, stringing, strength and removal need a physical coupon.'])
    os.environ.setdefault('MPLCONFIGDIR','/tmp/524-v7-matplotlib')
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(12,5))
    for s in nearby_support:
        axes[0].plot(*s['points'][:,:2].T,color='#A0A0A0',linewidth=2,alpha=.8)
    for s in first:
        axes[0].plot(*s['points'][:,:2].T,color='#D29D00',linewidth=2)
    axes[0].set(xlim=(125,131),ylim=(y_origin+37,y_origin+46),title='First hook layer / support below')
    for s in selected:
        pts=s['points']
        if pts[:,0].min()<=129.3 and pts[:,0].max()>=126.7:
            axes[1].plot(pts[:,1]-center[1],pts[:,2]-center[2],
                         color='#D29D00' if s['category']=='model' else '#AAAAAA',alpha=.35,linewidth=.6)
    axes[1].add_patch(plt.Circle((0,0),1.,fill=False,color='blue',linewidth=2))
    axes[1].set(xlim=(-5,5),ylim=(-5,5),title='Hook side toolpaths / 2 mm clear gauge')
    for ax in axes: ax.set_aspect('equal');ax.grid(alpha=.2)
    fig.tight_layout();fig.savefig(path.parent/'hook-toolpaths.png',dpi=150);plt.close(fig)
    (path.parent/'hook-verification.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input');parser.add_argument('--y-origin',type=float,default=180)
    args=parser.parse_args()
    result=inspect(args.input,args.y_origin)
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if all(result['checks'].values()) else 2)
