from pathlib import Path
import sys,json
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from build import *
from render import draw,plt
from matplotlib.path import Path as MPath
from matplotlib.patches import PathPatch,Circle
m=build_models(json.loads(Path('design.json').read_text()));pieces=m['assemblies']['star']
fig=plt.figure(figsize=(16,9),facecolor='#0b1220')
views=[('FRONT / 150 mm',0,-90,pieces),('SIDE / 8 mm bead',0,-28,pieces),('CUTAWAY / empty shell',10,-145,[(n,s.trim_by_plane([1,0,0],0)) for n,s in pieces])]
for i,(title,elev,azim,p) in enumerate(views):
 ax=fig.add_subplot(1,3,i+1)
 if i<2:
  draw(ax,p,elev=elev,azim=azim)
 else:
  contours=m['parts']['star_body'].rotate([0,90,0]).slice(0).to_polygons()
  paths=[]
  for poly in contours:
   points=np.vstack([poly,poly[0]])
   paths.append(MPath(points,[MPath.MOVETO]+[MPath.LINETO]*(len(poly)-1)+[MPath.CLOSEPOLY]))
  ax.add_patch(PathPatch(MPath.make_compound_path(*paths),facecolor='#2676c8',edgecolor='#83b6eb',lw=.5))
  ax.add_patch(Circle((27.5,0),4,facecolor='#d71830'))
  ax.text(-2,-27,'Hollow',color='#e4eaf6',fontsize=11,ha='center')
  ax.set_aspect('equal');ax.set_xlim(-35,48);ax.set_ylim(-84,68);ax.axis('off')
  ax.set_facecolor('#0b1220')
 ax.set_title(title,color='#eff4ff',fontsize=15)
fig.text(.055,.92,'RAMIEL / STAR FORM V2',color='#eff4ff',fontsize=26,weight='bold')
fig.text(.055,.85,'One-piece hollow blue body + aftermarket red bead + black stand',color='#b9c6dc',fontsize=15)
fig.text(.055,.1,'150 mm wide  /  154.7 mm on stand  /  nominal wall 1.2 mm  /  no internal grid or pins',color='#b9c6dc',fontsize=13)
fig.text(.055,.045,'Actual CAD geometry. Opaque shading, not an optical simulation. Rear and depth are design interpretations.',color='#8ca6cb',fontsize=11)
fig.subplots_adjust(left=.01,right=.99,bottom=.16,top=.78,wspace=-.1)
fig.savefig('printing/star-v2/star-design.png',dpi=150,facecolor=fig.get_facecolor());plt.close(fig)
print('rendered')
