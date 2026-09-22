"""Render dimensioned v6 design checks directly from the generated geometry."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build import ROOT, build_models, to_mesh, md, np
from render import plt, draw
from matplotlib.collections import PolyCollection
from scipy.spatial import ConvexHull

model = build_models(json.loads((ROOT / 'design.json').read_text()))
body = to_mesh(model['parts']['star_body'])
land = model['star_landmarks']
fig = plt.figure(figsize=(16, 11), facecolor='#0b1220')
ax = fig.add_subplot(2, 2, 1)
order = np.argsort(body.triangles_center[:, 0])
tri = body.triangles[order]
shade = .5 + .5 * np.maximum(body.face_normals[order] @ np.array([.8, -.3, .5]), 0)
colors = np.clip(np.array([.08, .4, .86])[None, :] * shade[:, None], 0, 1)
ax.add_collection(PolyCollection(tri[:, :, [2, 1]] * np.array([-1, 1]), facecolors=colors, edgecolors='none'))
tip = np.array(land['front_tips'])[:, 2].max()
ax.axvline(-3.2, color='#f0616c', lw=1, ls='--')
ax.axvline(-tip, color='#62aaff', lw=.8, ls=':')
ax.annotate('', xy=(-tip, 79), xytext=(-3.2, 79), arrowprops=dict(arrowstyle='<->', color='#fff'))
ax.text(-(tip + 3.2) / 2, 82, f'{tip-3.2:.1f} mm ahead of core', ha='center', color='white', fontsize=10)
ax.text(-3.2, -89, 'Core front plane', color='#f0616c', ha='center', fontsize=10)
ax.text(30, 45, 'Compact\nrear', color='#9eb7dc', ha='center')
ax.set_xlim(-50, 42); ax.set_ylim(-94, 92); ax.set_aspect('equal')
ax.set_title('01 / TRUE SIDE PROFILE — front at left', color='white', fontsize=12)
ax.set_facecolor('#0b1220'); ax.tick_params(colors='#94afd0'); ax.set_xlabel('mm along front / rear axis', color='#94afd0')

ax = fig.add_subplot(2, 2, 2, projection='3d')
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
q = np.array(land['arm_bases'])[1]; apex = np.array(land['front_tips'])[1]
faces = [[q[i], q[(i+1)%4], apex] for i in range(4)]
ax.add_collection3d(Poly3DCollection(faces, facecolors=['#1754a3','#2476dc','#215eb3','#3987e2'], edgecolors='#9ec8ff', linewidths=.8, alpha=.85))
closed = np.vstack([q, q[0]])
ax.plot(*closed.T, color='#79e4ce', lw=3)
for i, pt in enumerate(q): ax.text(*pt, f'  {i+1}', color='#b9ffeb', fontsize=12)
ax.scatter(*apex, color='white', s=16)
xyz = np.vstack([q, [apex]]); mid=xyz.mean(axis=0); half=np.ptp(xyz,axis=0).max()/2
ax.set_xlim(mid[0]-half,mid[0]+half); ax.set_ylim(mid[1]-half,mid[1]+half); ax.set_zlim(mid[2]-half,mid[2]+half)
ax.set_box_aspect([1,1,1]); ax.view_init(24, -55); ax.set_axis_off(); ax.set_facecolor('#0b1220')
ax.set_title('02 / ONE ARM — four coplanar root corners + apex', color='white', fontsize=12)

ax=fig.add_subplot(2,2,3)
draw(ax, [('star_base', model['parts']['star_base'])], 46, -65)
ax.set_title('03 / CITY ONLY — roofs follow the lower body',color='white',fontsize=12)

ax=fig.add_subplot(2,2,4); ax.set_facecolor('#0b1220')
from matplotlib.patches import Circle
ax.add_patch(Circle((0,-14),62, fill=False, ec='#7c8da9', lw=1))
for x,y,w,d,h,kind in model['city_buildings']:
 ax.add_patch(plt.Rectangle((x-w/2,y-d/2),w,d,fill=False,ec='#48546b',lw=.8))
p=np.array(model['city_support']['points_xy_z_gap_normal'])
ax.scatter(p[:,0],p[:,1],c='#73dbc9',s=12,marker='s', label='Near-contact roof samples')
hull=ConvexHull(p[:,:2]);boundary=p[hull.vertices,:2];boundary=np.vstack([boundary,boundary[0]])
ax.plot(boundary[:,0],boundary[:,1],'--',color='#8cead4',lw=1)
com=model['city_support']['uniform_shell_com_mm'];ax.scatter(*com[:2],c='#ffdf75',marker='x',s=90,label='Shell centre of mass')
for x,y,z in model['star_tip_positions_world']:
 if -63<x<63 and -77<y<49:ax.add_patch(Circle((x,y),7.5, fill=False, ec='#ea8585', lw=1))
ax.set_xlim(-66,66);ax.set_ylim(-80,51);ax.set_aspect('equal');ax.tick_params(colors='#94afd0');ax.set_xlabel('mm',color='#94afd0');ax.set_ylabel('mm',color='#94afd0')
ax.legend(loc='upper right',fontsize=8,facecolor='#1a293e',labelcolor='white',edgecolor='none')
ax.set_title('04 / SUPPORT MAP — tips kept clear',color='white',fontsize=12)
fig.suptitle('RAMIEL STAR V6 / FOUR DESIGN CHECKS',color='white',fontsize=21)
fig.text(.05,.025,'Actual CAD geometry. Roof samples indicate potential contact with clearance, not measured load capacity. Core: aftermarket 3 mm bead.',color='#9cb5d7',fontsize=10)
fig.subplots_adjust(top=.91,bottom=.09,hspace=.3,wspace=.15)
fig.savefig(ROOT/'printing/star-v6/design-checks.png',dpi=140,facecolor=fig.get_facecolor());plt.close(fig)
