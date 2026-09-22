"""A1–A4 cloud hats, editable CAD in millimetres. Front is -Y."""
from pathlib import Path
from functools import lru_cache
import sys
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'production-v1'))
import models as base
import numpy as np
import manifold3d as md
import trimesh
from skimage.measure import marching_cubes
ROOT=Path(__file__).resolve().parent
Part,Design=base.Part,base.Design
mesh,print_solid=base.mesh,base.print_solid
COLORS=base.COLORS


def portable_mesh(solid):
    """Weld float32-coincident vertices and remove only collapsed triangles."""
    original=mesh(solid)
    result=trimesh.Trimesh(original.vertices.astype(np.float32),original.faces,process=True)
    # Vertex welding may create zero-area faces; preserve valid thin triangles.
    if not result.is_watertight:
        result.update_faces(result.nondegenerate_faces(height=1e-12))
        result.remove_unreferenced_vertices()
    if np.any(result.area_faces==0):
        # Float32 can also leave a collinear facet in a closed mesh. Weld its
        # near-coincident edge at 0.00001 mm before removing it, so neighbours
        # keep a shared edge in both assembly and bed-translated coordinates.
        result.merge_vertices(digits_vertex=5)
        result.update_faces(result.nondegenerate_faces(height=1e-12))
        result.remove_unreferenced_vertices()
    assert result.is_watertight and result.is_volume and result.body_count==1
    assert np.all(result.area_faces>0)
    assert np.allclose(result.bounds,original.bounds,atol=1e-5)
    assert np.isclose(result.volume,original.volume,rtol=1e-5)
    return result

# Each lobe is ((width, depth, height), (x, y, z)) at master dimensions.
LOBES={
 'A1':[((35,31,20),(-17,-.5,48)),((38,32,24),(3,0,53)),((26,26,19),(20,0,51))],
 'A2':[((35,36,28),(-31,-1,40)),((42,38,29),(-9,-3,43)),((40,38,27),(17,-2,42)),((33,33,27),(36,0,40)),((43,36,30),(-3,6,52))],
 'A3':[((30,31,31),(-25,0,48)),((33,33,33),(-13,-1,61)),((33,35,33),(11,0,63)),((28,31,30),(27,1,49)),((23,26,26),(-30,1,34)),((22,27,26),(31,2,36)),((32,28,32),(0,9,62)),((26,29,24),(0,-3,51))],
 'A4':[((43,32,26),(-3,0,47)),((35,31,22),(-20,-2,41)),((32,30,22),(18,-1,44)),((26,26,26),(31,1,34)),((18,24,20),(41,1,23))]
}


def smooth_cloud(lobes,step=.40,blend=2.1):
    """Analytic ellipsoid fields avoid pixel-distance banding on rounded lobes."""
    centers=np.array([c for size,c in lobes],dtype=float)
    radii=np.array([size for size,c in lobes],dtype=float)/2
    low=np.min(centers-radii,axis=0)-blend-1
    high=np.max(centers+radii,axis=0)+blend+1
    axes=[np.arange(a,b+step,step,dtype=np.float32) for a,b in zip(low,high)]
    x,y,z=np.meshgrid(*axes,indexing='ij',sparse=True)
    field=None
    for r,c in zip(radii,centers):
        d=(np.sqrt(((x-c[0])/r[0])**2+((y-c[1])/r[1])**2+((z-c[2])/r[2])**2)-1)*min(r)
        if field is None:field=d
        else:
            h=np.clip(.5+.5*(d-field)/blend,0,1)
            field=d*(1-h)+field*h-blend*h*(1-h)
    verts,faces,_,_=marching_cubes(field,0,spacing=(step,step,step))
    verts+=np.array([a[0] for a in axes])
    result=trimesh.Trimesh(verts,faces,process=True);result.fix_normals()
    return base.from_mesh(result).simplify(.016)


def sleepy_eyes(parts,z):
    for i,x in enumerate((-11,11),1):
        eye=base.rounded((6.4,2.65,3.6),.7,(x,-12.65,z))
        pocket=base.rounded((6.95,2.55,4.15),.75,(x,-12.1,z))
        parts[0].solid-=pocket
        eye=eye.trim_by_plane((0,-1,0),11.0)
        parts.append(Part(f'clawd_eye_{i}','black',eye))


def make_cloud_model(key):
    zscale={'A1':1.,'A2':.72,'A3':1.,'A4':.88}[key]
    body=base.standing_clawd().scale((1,1,zscale))
    body=body.trim_by_plane((0,0,1),.8)  # Four flat soles, no additional base.
    body=body.trim_by_plane((0,-1,0),-11.7)  # Flat rear for a repeatable print pose.
    head_z=45*zscale
    locator=base.rounded((18,10,4),1,(0,0,head_z+1))
    body+=locator
    parts=[Part('clawd','orange',body,'back',True)]
    if key=='A4':sleepy_eyes(parts,33*zscale)
    else:base.add_eyes(parts,0,[(-11,33*zscale),(11,33*zscale)],-12.5,5.5)
    cloud=smooth_cloud(LOBES[key])
    cloud=cloud.trim_by_plane((0,-1,0),-8.0)  # Rear flat; front remains rounded.
    # Sweep the body downwards in cloud coordinates. The hat can be lowered
    # vertically without trapping the shoulders, while retaining a broad key.
    # Open the socket all the way through the rear: avoid a sub-line-width
    # membrane between the shoulders and the cloud's flat printable back.
    sweep=md.Manifold.batch_hull([body.translate((0,dy,dz)) for dy in (0,40) for dz in (0,-90)])
    envelope=sweep.minkowski_sum(md.Manifold.sphere(.30,12))
    cloud-=envelope
    parts.append(Part('cloud','white',cloud,'back',True))
    return parts


@lru_cache(maxsize=4)
def build_clouds(height_mm=48.0):
    if not 40<=height_mm<=150:raise ValueError('Supported overall height is 40–150 mm')
    out={}
    for key in LOBES:
        parts=make_cloud_model(key)
        for p in parts:p.solid=p.solid.simplify(.04 if p.name=='cloud' else .008)
        bounds=np.vstack([mesh(p.solid).bounds for p in parts]);low=bounds.min(0);high=bounds.max(0)
        scale=float(height_mm/(high[2]-low[2]))
        parts=[Part(p.name,p.color,p.solid.translate((0,0,-low[2])).scale((scale,scale,scale)),p.orientation,p.support) for p in parts]
        out[key]=Design(key,parts,height_mm,scale)
    return out
