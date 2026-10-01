"""Compare the preserved v7 assembly with the current CAD, at identical angles."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build import ROOT, build_models, from_mesh
from render import plt, draw
import trimesh

out = ROOT / 'printing/star-v8'
old_scene = trimesh.load(out / 'comparison-source-v7.3mf', force='scene')
old = []
for node in old_scene.graph.nodes_geometry:
    transform, key = old_scene.graph[node]
    mesh = old_scene.geometry[key].copy()
    mesh.apply_transform(transform)
    name = 'star_base' if mesh.bounds[0, 2] < 1 else ('red_core' if mesh.extents.max() < 4 else 'star_body')
    old.append((name, from_mesh(mesh)))
model = build_models(json.loads((ROOT / 'design.json').read_text()))
new = model['assemblies']['star']
fig = plt.figure(figsize=(15, 11), facecolor='#0b1220')
for i, (pieces, title, elev, azim) in enumerate([
    (old, 'BEFORE / low city, exposed stems', 18, -90),
    (new, 'AFTER / taller buildings, small contacts', 18, -90),
    (old, 'BEFORE / side', 15, -20),
    (new, 'AFTER / stepped buildings around the bearings', 15, -20),
]):
    ax = fig.add_subplot(2, 2, i+1)
    draw(ax, pieces, elev, azim)
    ax.set_title(title, color='#eff4ff', fontsize=14)
fig.suptitle('RAMIEL / STEPPED CITY BUILDINGS', color='#eff4ff', fontsize=22)
fig.text(.06, .02, 'Actual CAD. Blue body and display pose unchanged. Opaque shading; physical fit has not been tested.', color='#9cb5d7', fontsize=10)
fig.subplots_adjust(top=.92, bottom=.07, hspace=.03, wspace=-.08)
fig.savefig(out/'base-comparison.png', dpi=150)
plt.close(fig)

fig = plt.figure(figsize=(10, 10), facecolor='#0b1220')
ax = fig.add_subplot(111)
draw(ax, new, 20, -65)
fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
fig.savefig(out/'assembly.png', dpi=150)
plt.close(fig)
