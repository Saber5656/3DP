"""Actual extrusion previews. Parser adapted from local molecular-models tool."""
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
    with zipfile.ZipFile(file) as z:
        code=z.read('Metadata/plate_1.gcode').decode()
        plate=ET.fromstring(z.read('Metadata/slice_info.config')).find('plate')
    paths=parse_paths(code)
    names={int(x.attrib['identify_id']):x.attrib['name'] for x in plate.findall('object')}
    coords=np.concatenate([x['points'] for x in paths])
    assert coords.min()>0 and coords.max()<256
    objects={}
    for obj,name in names.items():
        entries=[x for x in paths if x['object']==obj and 'support' not in x['feature'].lower() and x['feature']!='Brim']
        layers=sorted({x['layer'] for x in entries})
        assert layers[0]==1,(name,'not on bed')
        assert layers==list(range(1,layers[-1]+1)),(name,'missing object layer')
        objects[name]={'first_layer':layers[0],'last_layer':layers[-1],'moves':len(entries)}
    max_layer=max(x['layer'] for x in paths)
    levels=[1,max(2,max_layer//3),max(3,2*max_layer//3),max_layer]
    fig,axes=plt.subplots(2,2,figsize=(12,10),facecolor='#f6f4ef')
    for ax,level in zip(axes.flat,levels):
        current=[x for x in paths if x['layer']==level]
        for support in (False,True):
            pieces=[x['points'] for x in current if ('support' in x['feature'].lower())==support]
            ax.add_collection(LineCollection(pieces,colors='#cc7b3c' if support else '#245b91',linewidths=.45))
        ax.set_xlim(coords[:,0].min()-4,coords[:,0].max()+4);ax.set_ylim(coords[:,1].min()-4,coords[:,1].max()+4)
        ax.set_aspect('equal');ax.grid(alpha=.1);ax.set_title(f"L{level} / Z {current[0]['z']:.2f} mm")
    fig.suptitle(f'{file.stem} / ACTUAL G-CODE / blue=model, orange=support')
    fig.tight_layout();target=file.parent/(file.stem+'-layers.png');fig.savefig(target,dpi=125);plt.close(fig)
    return {'file':file.name,'all_objects_on_layer_1':True,'all_object_layer_ranges_continuous':True,
            'path_bounds_xy_mm':[coords.min(0).tolist(),coords.max(0).tolist()],'objects':objects,
            'preview':target.name,'scope':'Extrusion only, including tessellated arcs. No claim of physical support removability.'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('files',nargs='+',type=Path);args=p.parse_args()
    reports=[inspect(file) for file in args.files]
    (args.files[0].parent/'layers-validation.json').write_text(json.dumps(reports,indent=2)+'\n')
    print(json.dumps([{'file':r['file'],'objects':len(r['objects'])} for r in reports]))
