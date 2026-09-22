"""Inspect extrusion moves from a provisional slice; no printer connection."""
from pathlib import Path
import re,math,json
from collections import defaultdict
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import numpy as np
ROOT=Path(__file__).resolve().parent
path=ROOT/'design/slice-provisional/plate_1.gcode'
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
assert len(segments)==115,len(segments)
# The middle stem layer fixes the object position without including startup lines.
mid=np.array(segments[10.0]).reshape(-1,2);center=(mid.min(axis=0)+mid.max(axis=0))/2
selected=(.2,2.8,3.2,10.,20.,22.8)
fig,axes=plt.subplots(2,3,figsize=(13,6.5),facecolor='#fafaf8')
for ax,z in zip(axes.flat,selected):
 seg=np.array(segments[z])-center
 ax.add_collection(LineCollection(seg,linewidths=.55,colors='#276a7c'))
 ax.set_xlim(-26,26);ax.set_ylim(-13,13);ax.set_aspect('equal');ax.set_facecolor('#fafaf8')
 ax.set_title(f'Z = {z:.1f} mm');ax.set_xlabel('mm');ax.set_ylabel('mm');ax.grid(alpha=.15)
fig.suptitle('PROVISIONAL SLICE / fit 30 / 0.4 mm nozzle, 0.20 mm layers',fontsize=15)
fig.text(.04,.015,'115 layers. Geometry inspection only; actual nozzle, plate and machine-start configuration are not verified.',fontsize=10)
fig.tight_layout(rect=(0,.045,1,.94));fig.savefig(ROOT/'output/provisional-layers.png',dpi=150);plt.close(fig)
# No printing moves cross a conservative central portion of the open passage.
# This checks the central corridor, not all extrusion widths near the inner wall.
violations=[]
for z,segs in segments.items():
 for segment in np.asarray(segs):
  pts=np.linspace(segment[0]-center,segment[1]-center,9)
  if np.any((np.abs(pts[:,0])<10)&(np.abs(pts[:,1])<3)):
   violations.append(float(z));break
assert not violations,violations
report={'stage':'provisional geometry slice only','bambu_version':'02.08.02.61','nozzle_assumption_mm':.4,'layer_height_mm':.2,'material_assumption':'Bambu PLA Basic','layers':len(segments),'selected_layers':list(selected),'central_corridor_extrusion_violations':violations,'extruding_arcs':arc_extrusions,'actual_print':'NOT_RUN','startup_and_plate_configuration':'NOT_VERIFIED','estimated_time':'11m00s (provisional profile; not a prediction for the real setup)','estimated_filament_g':4.83}
(ROOT/'design/slice-provisional/inspection.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
