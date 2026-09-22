"""Inspect actual GUI-generated V3 extrusion paths; no printer connection."""
from pathlib import Path
import re,math,json
from collections import defaultdict
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import numpy as np
ROOT=Path(__file__).resolve().parent
path=ROOT/'output/body-v3/kirby-v3-5mmOD-black.gcode'
lines=path.read_text().splitlines()
state={'X':0.,'Y':0.,'Z':0.,'E':0.};absolute=True;relative_e=False;layer=None
segments=defaultdict(list); arc_extrusions=0
for line in lines:
 if line.startswith('; Z_HEIGHT:'):
  layer=round(float(line.split(':')[1]),3)
 cmd=line.split(';',1)[0].strip()
 if not cmd:continue
 words=cmd.split();op=words[0]
 vals={k:float(v) for k,v in re.findall(r'([XYZEFIJP])\s*(-?(?:\d+(?:\.\d*)?|\.\d+))',cmd)}
 if op=='M83':relative_e=True;continue
 if op=='M82':relative_e=False;continue
 if op=='G90':absolute=True;continue
 if op=='G91':absolute=False;continue
 if op=='G92':
  for k in ('X','Y','Z','E'):
   if k in vals: state[k]=vals[k]
  continue
 if op not in ('G0','G1','G2','G3'):continue
 old=state.copy()
 for k in ('X','Y','Z'):
  if k in vals:state[k]=vals[k]+(0 if absolute else old[k])
 delta_e=0
 if 'E' in vals:
  delta_e=vals['E'] if relative_e else vals['E']-old['E']
  state['E']=old['E']+delta_e
 if layer is None or delta_e<=1e-8:continue
 if op in ('G2','G3'):
  arc_extrusions+=1
  cx,cy=old['X']+vals.get('I',0),old['Y']+vals.get('J',0)
  a=math.atan2(old['Y']-cy,old['X']-cx);b=math.atan2(state['Y']-cy,state['X']-cx)
  if op=='G3':
   while b<=a+1e-8:b+=2*math.pi
  else:
   while b>=a-1e-8:b-=2*math.pi
  radius=math.hypot(old['X']-cx,old['Y']-cy)
  ts=np.linspace(a,b,max(8,int(abs(b-a)*radius/.4)))
  pts=np.c_[cx+radius*np.cos(ts),cy+radius*np.sin(ts)]
  segments[layer].extend(np.stack([pts[:-1],pts[1:]],axis=1).tolist())
 elif (state['X'],state['Y'])!=(old['X'],old['Y']):
  segments[layer].append([[old['X'],old['Y']],[state['X'],state['Y']]])

assert len(segments)==265,len(segments)
import zipfile,xml.etree.ElementTree as ET
with zipfile.ZipFile(ROOT/'output/body-v3/kirby-v3-5mmOD-X2D-black-PLA.3mf') as archive:
 settings=ET.fromstring(archive.read('Metadata/model_settings.config'))
 by_name={o.find("metadata[@key='name']").get('value'):o.get('id') for o in settings.findall('object')}
 positions={a.get('object_id'):np.array([float(v) for v in a.get('transform').split()][9:11]) for a in settings.findall('assemble/assemble_item') if a.get('instance_id') is not None}
 centers=[positions[by_name[n]] for n in ('kirby_body_v3_5mm_OD',)]
# Conservative clear cores, including 0.5 mm allowance for extrusion width.
# Checks the exact line segments (arcs tessellated to <=0.4 mm), not just endpoints.
from shapely.geometry import LineString,Point
violations=[]
for z,segs in segments.items():
 for c,r,label in [(centers[0],1.,'body')]:
  if label=='nut' and z>8:continue
  core=Point(*c).buffer(r)
  if any(LineString(seg).intersects(core) for seg in segs):violations.append([z,label])
assert not violations,violations
selected=(.2,19.8,26.,42.8,46.,52.8)
fig,axes=plt.subplots(2,3,figsize=(15,7),facecolor='#fafaf8')
for ax,z in zip(axes.flat,selected):
 ax.add_collection(LineCollection(segments[z],linewidths=.45,colors='#276a7c'))
 ax.set_xlim(centers[0][0]-27,centers[0][0]+27);ax.set_ylim(101,151);ax.set_aspect('equal')
 ax.set_title(f'Z = {z:.1f} mm');ax.set_xlabel('mm');ax.grid(alpha=.15)
fig.suptitle('V3 actual GUI slice / X2D / BLACK PLA / 0.20 mm / 265 layers',fontsize=15)
fig.text(.03,.01,'The central passage remains open. This is a geometry/toolpath check; physical fit, seal and print completion are not verified.',fontsize=10)
fig.tight_layout(rect=(0,.04,1,.94));fig.savefig(ROOT/'output/body-v3/layers.png',dpi=130);plt.close(fig)
report={'source':str(path.relative_to(ROOT)),'stage':'actual GUI slice','layers':len(segments),'selected_layers_mm':list(selected),'central_clear_core_violations':violations,'core_radii_mm':{'body':1.0},'extruding_arcs':arc_extrusions,'scope':'all-layer conservative core clearance plus six plotted XY layers; not full passage/strength verification','estimated_time':'34m15s','estimated_filament_g':10.61}
(ROOT/'design/body-v3/layer-inspection.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
