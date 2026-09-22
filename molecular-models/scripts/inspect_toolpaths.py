"""Inspect actual sliced object paths, excluding travel and start/end macros."""
import argparse
from collections import Counter
import hashlib
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection


def parse_paths(code):
    xy=np.zeros(2);e=0.;relative=False;layer=0;z=0.;feature='Custom';obj=-1;paths=[]
    for line in code.splitlines():
        if line.startswith('; CHANGE_LAYER'):layer+=1
        elif line.startswith('; Z_HEIGHT:'):z=float(line.split(':')[1])
        elif line.startswith('; FEATURE:'):feature=line.split(':',1)[1].strip()
        elif line.startswith('; OBJECT_ID:'):obj=int(line.split(':')[1])
        command=line.split(';')[0].strip();op=command.split(' ')[0]
        values={k:float(v) for k,v in re.findall(r'([XYEIJ])([-+]?\d*\.?\d+)',command)}
        if op=='M83':relative=True
        if op=='M82':relative=False
        if op=='G92':
            e=values.get('E',e);continue
        if op not in {'G0','G1','G2','G3'}:continue
        end=np.array([values.get('X',xy[0]),values.get('Y',xy[1])])
        de=values.get('E',0) if relative else values.get('E',e)-e
        if 'E' in values:e=e+de if relative else values['E']
        if layer and de>0 and feature!='Custom' and (np.linalg.norm(end-xy)>1e-8 or op in {'G2','G3'}):
            points=np.array([xy,end])
            if op in {'G2','G3'}:
                if 'I' not in values and 'J' not in values:raise ValueError('Arc without centre offsets')
                centre=xy+[values.get('I',0),values.get('J',0)];radius=np.linalg.norm(xy-centre)
                start=np.arctan2(*(xy-centre)[::-1]);finish=np.arctan2(*(end-centre)[::-1])
                sweep=(finish-start)%(2*np.pi) if op=='G3' else -((start-finish)%(2*np.pi))
                if abs(sweep)<1e-9:sweep=2*np.pi if op=='G3' else -2*np.pi
                angles=np.linspace(start,start+sweep,max(4,int(np.ceil(abs(sweep)*radius/.15))+1))
                points=centre+radius*np.column_stack([np.cos(angles),np.sin(angles)])
                points[0]=xy;points[-1]=end
            paths.append(dict(layer=layer,z=z,feature=feature,object=obj,points=points))
        xy=end
    return paths


def inspect(file):
    out=file.parent.parent
    with zipfile.ZipFile(file) as archive:
        assert archive.testzip() is None
        code=archive.read('Metadata/plate_1.gcode').decode()
        settings=json.loads(archive.read('Metadata/project_settings.config'))
        slice_info=ET.fromstring(archive.read('Metadata/slice_info.config'))
    plate=slice_info.find('plate');meta={x.attrib['key']:x.attrib['value'] for x in plate.findall('metadata')}
    assert settings['printer_model']=='Bambu Lab X2D'
    assert settings['nozzle_diameter']==['0.4','0.4']
    assert float(settings['filament_density'][0])>1
    assert len(settings['machine_start_gcode'])>1000
    assert settings['enable_support']=='0'
    paths=parse_paths(code);max_layer=max(x['layer'] for x in paths)
    coords=np.concatenate([x['points'] for x in paths])
    assert coords.min()>0 and coords.max()<256
    names={int(x.attrib['identify_id']):x.attrib['name'] for x in plate.findall('object')}
    first_objects=set(x['object'] for x in paths if x['layer']==1 and x['feature']!='Brim')
    assert first_objects==set(names),'An object does not start on the bed'
    stats={}
    for obj,name in names.items():
        p=[x for x in paths if x['object']==obj and x['feature']!='Brim']
        stats[name]=dict(first_layer=min(x['layer'] for x in p),last_layer=max(x['layer'] for x in p),
            max_z_mm=max(x['z'] for x in p),features=dict(Counter(x['feature'] for x in p)))
    colors={'Outer wall':'#245b91','Inner wall':'#5693c4','Brim':'#beb7a5','Bottom surface':'#d38b36',
        'Top surface':'#cf6748','Sparse infill':'#63a58b','Internal solid infill':'#8b9f51','Gap infill':'#777777',
        'Bridge':'#a468af','Floating vertical shell':'#a7864b'}
    levels=[1,14,22,max_layer]
    fig,axes=plt.subplots(2,2,figsize=(13,12),facecolor='#f6f4ef')
    for ax,level in zip(axes.flat,levels):
        current=[x for x in paths if x['layer']==level]
        for kind in sorted(set(x['feature'] for x in current)):
            ax.add_collection(LineCollection([x['points'] for x in current if x['feature']==kind],colors=colors.get(kind,'black'),linewidths=.6))
        ax.set_xlim(coords[:,0].min()-5,coords[:,0].max()+5);ax.set_ylim(coords[:,1].min()-5,coords[:,1].max()+5)
        ax.set_aspect('equal');ax.set_facecolor('#ffffff');ax.grid(alpha=.12)
        ax.set_title(f"LAYER {level} / Z {current[0]['z']:.2f} mm",loc='left',weight='bold')
        ax.set_xlabel('X / mm');ax.set_ylabel('Y / mm')
    fig.suptitle('FIRST TRIAL / ACTUAL SLICED TOOLPATHS',fontsize=21,weight='bold',x=.08,ha='left')
    fig.text(.08,.032,'X2D 0.4 mm | PLA black | 0.16 mm layers (first 0.20) | support off | final physical checks required before printing',fontsize=10)
    fig.tight_layout(rect=[.035,.06,1,.94]);fig.savefig(out/'layer-preview.png',dpi=150);plt.close(fig)
    # Macro T65279/T65535 are preserved from the official machine-end template;
    # they occur after object extrusion and trigger the CLI preview parser warnings.
    result=dict(status='Provisional slice verified; not sent to printer',package_sha256=hashlib.sha256(file.read_bytes()).hexdigest(),
        printer=settings['printer_model'],nozzle_mm=settings['nozzle_diameter'],bed=settings['curr_bed_type'],
        layer_count=max_layer,estimated_seconds=int(meta['prediction']),estimated_filament_g=float(meta['weight']),
        support_used=meta['support_used'],all_three_objects_start_on_layer_1=True,
        extrusion_path_bounds_mm=[coords.min(0).tolist(),coords.max(0).tolist()],objects=stats,
        first_layer_time='CLI metadata reports 0; do not use this field for estimates',
        warnings='CLI parser logs Invalid T65279/T65535 for unchanged official end-template unload macros; physical execution untested',
        unknowns=['physical nozzle installation beyond saved profile','current clear-bed state','physical fit and strength'],
        gcode_preview_scope='Object extrusion paths including G2/G3 arcs; travel and startup/end macros excluded. Not a firmware simulator.')
    (out/'slice-validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('file',type=Path);inspect(p.parse_args().file)
