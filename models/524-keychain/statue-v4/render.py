"""Orthographic views rasterized from actual CAD meshes, not concept art."""
import os
os.environ.setdefault('MPLCONFIGDIR', '/tmp/524-keychain-matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from build import build_model, as_mesh, ROOT, COLORS, orient_for_print

def draw(ax, pieces, elev=15, azim=-67, mono=False, focus=None, span=None):
    meshes = []
    for name, solid in pieces:
        mesh = as_mesh(solid)
        meshes.append((name, mesh))
    # Orthographic software rasterizer with a per-pixel depth buffer. This avoids
    # painter-sort errors between touching assemblies or a core inside its seat.
    el, az = np.deg2rad([elev, azim])
    eye = np.array([np.cos(el)*np.cos(az), np.cos(el)*np.sin(az), np.sin(el)])
    right = np.cross([0., 0., 1.], eye); right /= np.linalg.norm(right)
    up = np.cross(eye, right)
    basis = np.array([right, up, eye]).T
    all_vertices = np.vstack([m.vertices for _, m in meshes]) @ basis
    lo, hi = all_vertices.min(axis=0), all_vertices.max(axis=0)
    center = (lo + hi)/2
    if focus is not None:
        center = np.asarray(focus) @ basis
    width, height = 720, 720
    scale = min((width-100)/(hi[0]-lo[0]), (height-100)/(hi[1]-lo[1]))
    if span is not None:
        scale = (width-100)/span
    rgb = np.empty((height, width, 3), dtype=np.uint8); rgb[:] = [242, 241, 236]
    depth = np.full((height, width), -np.inf)
    light = eye * .75 + up * .9 - right * .35; light /= np.linalg.norm(light)
    for name, mesh in meshes:
        projected = mesh.vertices @ basis
        projected[:, 0] = (projected[:, 0]-center[0])*scale + width/2
        projected[:, 1] = -(projected[:, 1]-center[1])*scale + height/2
        base = np.array([.76, .79, .84]) if mono else np.asarray([int(COLORS[name][k:k+2],16) for k in (1,3,5)])/255
        strength = .47 + .53*np.maximum(0, mesh.face_normals @ light)
        colors = np.clip(strength[:, None]*base*255, 0, 255).astype(np.uint8)
        for index, f in enumerate(mesh.faces):
            a, b, c = projected[f]
            xmin = max(0, int(np.floor(min(a[0], b[0], c[0]))))
            xmax = min(width-1, int(np.ceil(max(a[0], b[0], c[0]))))
            ymin = max(0, int(np.floor(min(a[1], b[1], c[1]))))
            ymax = min(height-1, int(np.ceil(max(a[1], b[1], c[1]))))
            if xmin > xmax or ymin > ymax:
                continue
            denom = (b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
            if abs(denom) < 1e-10:
                continue
            ys, xs = np.mgrid[ymin:ymax+1, xmin:xmax+1]
            xs, ys = xs+.5, ys+.5
            u = ((b[1]-c[1])*(xs-c[0])+(c[0]-b[0])*(ys-c[1]))/denom
            v = ((c[1]-a[1])*(xs-c[0])+(a[0]-c[0])*(ys-c[1]))/denom
            w = 1-u-v
            z = u*a[2]+v*b[2]+w*c[2]
            old = depth[ymin:ymax+1, xmin:xmax+1]
            mask = (u >= -1e-8) & (v >= -1e-8) & (w >= -1e-8) & (z > old)
            old[mask] = z[mask]
            rgb[ymin:ymax+1, xmin:xmax+1][mask] = colors[index]
    ax.imshow(rgb)
    ax.set_axis_off()
    ax.set_facecolor("#f2f1ec")

def main():
    model=build_model();parts=list(model['parts'].items())
    for mono, filename in [(False,'preview.png'),(True,'solid-review.png')]:
        fig, axes=plt.subplots(2,2,figsize=(11,10),facecolor='#f2f1ec')
        for ax,(label,elev,azim) in zip(axes.flat,[('FRONT / traced artwork',0,-90),('3/4 / rounded volume',18,-57),('SIDE / rear eyelet',5,0),('REAR / yellow body',12,90)]):
            draw(ax,parts,elev=elev,azim=azim,mono=mono)
            ax.set_title(label,fontsize=11,color='#46433d',loc='left',pad=-2)
        fig.suptitle('524 / WOOD SCULPTURE SHAPE / 40 mm',fontsize=22,color='#302e29',weight='bold',y=.97)
        fig.text(.055,.035,'Actual CAD geometry / colors approximate / clasp fit and printing not yet tested',fontsize=10,color='#69655d')
        fig.subplots_adjust(left=.035,right=.98,bottom=.08,top=.92,wspace=.01,hspace=.05)
        fig.savefig(ROOT/'output'/filename,dpi=140,facecolor=fig.get_facecolor());plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(11, 6), facecolor='#f2f1ec')
    for ax, include_dots, label in zip(axes, [False, True],
                                      ['BODY ONLY / 40 mm overall',
                                       'WITH DOTS / added yellow stems']):
        draw(ax, list(build_model(include_dots)['parts'].items()), elev=12, azim=-75)
        ax.set_title(label, fontsize=12, color='#46433d')
    fig.suptitle('524 / TWO PHYSICAL OPTIONS', fontsize=21, color='#302e29', weight='bold')
    fig.text(.055,.04,'Both: 40 mm main body / detached source marks require added connecting stems',
             fontsize=10,color='#69655d')
    fig.subplots_adjust(left=.02,right=.98,bottom=.09,top=.85,wspace=.04)
    fig.savefig(ROOT/'output'/'options.png',dpi=140,facecolor=fig.get_facecolor())
    plt.close(fig)
    fig, axes = plt.subplots(1, 3, figsize=(14, 6), facecolor='#f2f1ec')
    for ax, elev, azim, title in zip(axes[:2], [0, 25], [0, 45],
                                  ['SIDE / 6.8 mm round loop', 'REAR DETAIL / small exposed arc']):
        draw(ax, parts, elev=elev, azim=azim, focus=model["eyelet_center"], span=13)
        ax.set_title(title, fontsize=11, color='#46433d')
    draw(axes[2], list(orient_for_print(model['parts']).items()), elev=40, azim=-70)
    axes[2].set_title('PRINT ORIENTATION / face up', fontsize=11, color='#46433d')
    fig.suptitle('524 / COMPACT REAR LOOP', fontsize=23, color='#302e29', weight='bold')
    fig.text(.04,.07,'2.4 mm clear passage checked in CAD / 1.8 mm round section / rear-facing supports required',
             fontsize=11,color='#69655d')
    fig.subplots_adjust(left=.02,right=.98,bottom=.1,top=.8,wspace=.02)
    fig.savefig(ROOT/'output'/'rear-loop-detail.png',dpi=150,facecolor=fig.get_facecolor())
    plt.close(fig)
    import trimesh
    import manifold3d as m
    old_scene = trimesh.load(ROOT/'source/previous-keychain-v3.glb', force='scene')
    previous = [(name, m.Manifold(m.Mesh64(mesh.vertices, np.asarray(mesh.faces, dtype=np.uint64))))
                for name,mesh in old_scene.geometry.items()]
    import json
    balance = json.loads((ROOT/'output/balance-report.json').read_text())
    fig, axes = plt.subplots(2,2,figsize=(12,10),facecolor='#f2f1ec')
    for col,(pieces,label,info) in enumerate([(previous,'PREVIOUS / loop height 32.1 mm',balance['previous_v3']),
                                               (parts,'RAISED / loop height 36.0 mm',balance['current_v4'])]):
        draw(axes[0,col], pieces, elev=0, azim=0, span=53)
        axes[0,col].set_title(label, fontsize=13, color='#46433d')
        angle = info['pitch_center_proxy_deg']
        center = np.asarray(info['eyelet_center'])
        tilted = [(name,solid.translate(-center).rotate([angle,0,0])) for name,solid in pieces]
        draw(axes[1,col], tilted, elev=0, azim=0, span=53)
        axes[1,col].set_title(f'IDEALIZED HANGING / pitch {angle:.1f} deg',fontsize=12,color='#46433d')
    fig.suptitle('524 / HIGHER LOOP, LESS FORWARD PITCH',fontsize=21,weight='bold')
    fig.text(.04,.043,'Top: actual CAD / bottom: pitch estimate from model extrusion, not a physical test',fontsize=11)
    fig.text(.04,.018,'Same 40 mm body / ring-centre contact proxy / equal PLA density / clasp friction and roll not modeled',fontsize=10)
    fig.subplots_adjust(left=.02,right=.98,bottom=.08,top=.91,wspace=.01,hspace=.08)
    fig.savefig(ROOT/'output'/'loop-position-comparison.png',dpi=150,facecolor=fig.get_facecolor())
    plt.close(fig)
    print('Saved previews and loop-position-comparison.png')

if __name__=='__main__':main()
