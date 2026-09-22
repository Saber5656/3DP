"""Editable parametric desk sculptures. Millimetres; front faces negative Y."""
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import math
import numpy as np
import manifold3d as md
import trimesh
from PIL import Image
from shapely.geometry import Polygon, Point
from shapely import affinity
from svgpathtools import svg2paths
from skimage.measure import find_contours, marching_cubes
from scipy.ndimage import distance_transform_edt, binary_fill_holes, gaussian_filter

ROOT=Path(__file__).resolve().parent
COLORS={'white':'#F4F0E6','black':'#26282D','orange':'#E17D50',
        'translucent_blue':'#5377DB','gray':'#B8B5AE'}
MASTER_CLEARANCE=.30  # About 0.20 mm per side at the nominal 48 mm output.


@dataclass
class Part:
    name: str
    color: str
    solid: object
    orientation: str='back'
    support: bool=False


@dataclass
class Design:
    name: str
    parts: list
    height_mm: float
    scale: float


def mesh(solid):
    d=solid.to_mesh64()
    return trimesh.Trimesh(np.asarray(d.vert_properties)[:,:3],np.asarray(d.tri_verts),process=True)


def from_mesh(m):
    return md.Manifold(md.Mesh64(np.asarray(m.vertices,dtype=np.float64),np.asarray(m.faces,dtype=np.uint64)))


def union(items):
    return md.Manifold.batch_boolean(list(items),md.OpType.Add)


@lru_cache(maxsize=128)
def _rounded(size,r):
    return md.Manifold.cube(np.asarray(size)-2*r,center=True).minkowski_sum(md.Manifold.sphere(r,32))


def rounded(size,r=3,at=(0,0,0)):
    return _rounded(tuple(size),min(r,min(size)/2-.01)).translate(at)


def oval(size,at=(0,0,0)):
    return md.Manifold.sphere(1,48).scale(np.asarray(size)/2).translate(at)


def polygon_cs(poly):
    rings=[np.asarray(poly.exterior.coords)[:,:2]]
    rings.extend(np.asarray(h.coords)[:,:2] for h in poly.interiors)
    return md.CrossSection(rings,md.FillRule.EvenOdd)


@lru_cache(maxsize=32)
def logo_polygon(width):
    paths,_=svg2paths(str(ROOT/'sources/chatgpt-blossom.svg'))
    rings=[]
    for path in paths:
        for sub in path.continuous_subpaths():
            xy=[]
            for seg in sub:
                n=max(2,int(math.ceil(seg.length()/1.5)))
                xy.extend((seg.point(t).real,-seg.point(t).imag) for t in np.linspace(0,1,n,endpoint=False))
            rings.append(Polygon(xy))
    rings.sort(key=lambda p:p.area,reverse=True)
    shape=Polygon(rings[0].exterior.coords,[r.exterior.coords for r in rings[1:]])
    x0,y0,x1,y1=shape.bounds
    shape=affinity.translate(shape,-(x0+x1)/2,-(y0+y1)/2)
    return affinity.scale(shape,xfact=width/(x1-x0),yfact=width/(x1-x0),origin=(0,0))


def relief(poly,depth,at):
    # Polygon y becomes display Z. Extrusion goes toward the viewer (-Y).
    return polygon_cs(poly).extrude(depth).rotate((90,0,0)).translate(at)


def add_logo(parts,body_index,width,front_y,z,x=0):
    poly=logo_polygon(width)
    # 0.20 mm assembly clearance at nominal final 48 mm size, glue-in insert.
    cavity=relief(poly.buffer(.28),2.25,(x,front_y+1.55,z))
    body=parts[body_index]
    body.solid=body.solid-cavity
    insert=relief(poly,3.6,(x,front_y+1.4,z))
    parts.append(Part(body.name+'_logo','black',insert))


def add_eyes(parts,body_index,centers,front_y,size=5):
    body=parts[body_index]
    for i,(x,z) in enumerate(centers):
        eye=rounded((size,2.5,size),.65,(x,front_y-.05,z))
        pocket=rounded((size+.5,2.25,size+.5),.8,(x,front_y+.4,z))
        body.solid=body.solid-pocket
        # Remove the rear overlap from eye, preserving a planar glue surface.
        eye=eye.trim_by_plane((0,-1,0),-front_y-1.05)
        parts.append(Part(body.name+f'_eye_{i+1}','black',eye))


@lru_cache(maxsize=1)
def codex_polygons():
    im=np.asarray(Image.open(ROOT.parent/'references/codex-app-light.png').convert('RGBA'))
    rgb=im[:,:,:3].astype(float);alpha=im[:,:,3]>200
    color=alpha & (rgb[:,:,2]>rgb[:,:,0]+24) & (rgb[:,:,2]>rgb[:,:,1]+8)
    filled=binary_fill_holes(color)
    contours=find_contours(filled,.5)
    outer=max(contours,key=len)
    shape=Polygon([(p[1],-p[0]) for p in outer]).simplify(.65)
    x0,y0,x1,y1=shape.bounds;cx,cy=(x0+x1)/2,(y0+y1)/2
    shape=affinity.translate(shape,-cx,-cy)
    white=filled & (rgb.min(axis=2)>205) & ((rgb.max(axis=2)-rgb.min(axis=2))<50)
    glyphs=[]
    for c in find_contours(white,.5):
        poly=Polygon([(p[1]-cx,-p[0]-cy) for p in c]).simplify(.7)
        if poly.area>200:glyphs.append(poly)
    glyphs=sorted(glyphs,key=lambda p:p.area,reverse=True)[:2]
    return shape,glyphs,x1-x0


def codex(width,depth,at):
    poly,glyphs,w=codex_polygons();s=width/w
    shape=affinity.scale(poly,s,s,origin=(0,0))
    # Rounded front lip, shallow baseline extrusion maintains source silhouette.
    body=relief(shape,depth,at)
    low=body.bounding_box()[2]
    # A hidden tongue gives the flower a real seat rather than point contact.
    x,y,z=at
    body+=rounded((20,8,low+1),1,(x,y-depth/2,(low+7)/2))
    parts=[Part('codex_flower','translucent_blue',body)]
    x,y,z=at
    for i,g in enumerate(glyphs):
        gp=affinity.scale(g,s,s,origin=(0,0))
        parts[0].solid-=relief(gp.buffer(.28),2.15,(x,y-depth+1.5,z))
        parts.append(Part(f'codex_glyph_{i+1}','white',relief(gp,3.0,(x,y-depth+1.3,z))))
    return parts


def standing_clawd():
    body=rounded((44,25,34),6,(0,0,28))
    feet=[rounded((10,11,15),3,(x,y,7.5)) for x in (-13,13) for y in (-6,6)]
    arms=[rounded((9,15,15),3.5,(x,0,26)) for x in (-24,24)]
    return union([body,*feet,*arms])


def clip_floor(s,z):
    return s.trim_by_plane((0,0,1),z)


def glue_envelope(s):
    return s.minkowski_sum(md.Manifold.sphere(MASTER_CLEARANCE,12))


def mochi_knot():
    """Rounded 3D extrusion of the actual 7-hole knot, flat printable back."""
    from shapely import contains_xy
    p=logo_polygon(66).buffer(1.35)
    step=.22
    xs=np.arange(-36,36+step,step);ys=xs.copy();zs=np.arange(-1,9+step,step)
    xx,yy=np.meshgrid(xs,ys,indexing='ij')
    inside=contains_xy(p,xx,yy)
    sd=(distance_transform_edt(~inside)-distance_transform_edt(inside))*step
    # Tubular rounded bands; retain the seven actual negative spaces.
    r=2.5;qx=sd[:,:,None]+r;qz=np.abs(zs[None,None,:]-3.9)-3.9+r
    sdf=np.sqrt(np.maximum(qx,0)**2+np.maximum(qz,0)**2)+np.minimum(np.maximum(qx,qz),0)-r
    sdf=gaussian_filter(sdf,.65)
    verts,faces,_,_=marching_cubes(sdf,0,spacing=(step,step,step))
    verts+=np.array([xs[0],ys[0],zs[0]])
    m=trimesh.Trimesh(verts,faces,process=True);m.fix_normals()
    s=from_mesh(m).trim_by_plane((0,0,1),.5).translate((0,0,-.5))
    tab=rounded((22,8,5),1,(0,-34,2.5))
    # In planar coordinates tab's Y points towards logo bottom.
    s=(s+tab).simplify(.008)
    return s.rotate((90,0,0)).translate((0,0,40))


def make_d1():
    knot=mochi_knot()
    base=rounded((60,31,7),3,(0,-5,3.5))
    # Cradle is an actual subtraction; glue fit, never an interference fit.
    cavity=rounded((22.6,5.6,6.5),.8,(0,-2.5,4.85))
    base=base-knot-cavity
    return [Part('knot','white',knot),Part('cradle','black',base,'bottom')]


def make_d2():
    tile=rounded((56,20,54),7,(0,0,45))
    feet=[rounded((14,26,22),6,(x,-10,15)) for x in (-14,14)]
    hands=[oval((12,16,25),(x,-1,30)) for x in (-29,29)]
    body=union([tile,*feet,*hands])
    seat=rounded((68,38,17),3,(0,3,8.5))
    seat-=glue_envelope(body)
    parts=[Part('seated_tile','white',body,support=True),Part('seat','gray',seat,'bottom')]
    add_logo(parts,0,42,-10,47)
    return parts


def make_d3():
    torso=rounded((55,29,52),7,(0,4,43))
    legs=[rounded((18,27,18),7,(x,-6,9)) for x in (-23,23)]
    arms=[rounded((14,25,30),6,(x,-12,36)) for x in (-25,25)]
    body=union([torso,*legs,*arms])
    pillow=rounded((41,15,43),6,(0,-13,26))
    envelope=glue_envelope(pillow)
    # Convex pillow slides from the front; remove its whole insertion path.
    body-=md.Manifold.batch_hull([envelope,envelope.translate((0,-60,0))])
    parts=[Part('hugging_clawd','orange',body,support=True),Part('pillow','white',pillow)]
    add_eyes(parts,0,[(-13,59),(13,59)],-10.5,5.5)
    add_logo(parts,1,30,-20.5,26)
    return parts


def make_pair(kind):
    base=rounded((122,42,7),3,(0,0,3.5))
    clawd=standing_clawd().rotate((0,11,0)).translate((-34,0,7))
    parts=[Part('clawd','orange',clawd,support=True)]
    # Place unrotated eyes in local body coordinate then apply same tilt.
    local=[Part('clawd','orange',standing_clawd())]
    add_eyes(local,0,[(-11,33),(11,33)],-12.5,5.5)
    parts=[Part(p.name,p.color,p.solid.rotate((0,11,0)).translate((-34,0,7)),p.orientation,p.support) for p in local]
    parts[0].support=True
    # Extend both pairs of tilted feet into the common locating plane.
    for foot_x in (-13,13):
        x=-34+math.cos(math.radians(11))*foot_x+math.sin(math.radians(11))*7.5
        for y in (-6,6):parts[0].solid+=rounded((8,9,9),2,(x,y,9.5))
    if kind=='D4':
        tile=rounded((58,17,63),7,(27,0,37))
        parts.append(Part('gpt_tile','white',tile))
        add_logo(parts,len(parts)-1,44,-8.5,37,27)
    else:
        parts.extend(codex(64,12,(27,5,39)))
    # End the feet on a common base plane and make shallow locating rebates.
    parts[0].solid=clip_floor(parts[0].solid,5.5)
    for p in parts:
        if 'eye' not in p.name and not p.name.endswith('logo') and 'glyph' not in p.name:
            base-=glue_envelope(p.solid)
    parts.append(Part('pair_base','black',base,'bottom'))
    # Preserve design contacts while removing physically impossible overlaps.
    other=next(p.solid for p in parts if p.name in ('gpt_tile','codex_flower'))
    parts[0].solid-=other
    return parts


@lru_cache(maxsize=4)
def build_all(height_mm=48.0):
    designs={}
    for key,parts in [('D1',make_d1()),('D2',make_d2()),('D3',make_d3()),('D4',make_pair('D4')),('B4',make_pair('B4'))]:
        for p in parts:
            p.solid=p.solid.simplify(.004)
            if p.name=='seat':p.solid=p.solid.simplify(.06)
        b=np.vstack([mesh(p.solid).bounds for p in parts]);lo=b.min(axis=0);hi=b.max(axis=0)
        scale=float(height_mm/(hi[2]-lo[2]))
        # Collapse sub-micron boolean slivers before float32 binary STL export.
        out=[Part(p.name,p.color,p.solid.translate((0,0,-lo[2])).scale((scale,scale,scale)),p.orientation,p.support) for p in parts]
        designs[key]=Design(key,out,height_mm,scale)
    return designs


def print_solid(part):
    s=part.solid
    if part.orientation=='back':s=s.rotate((-90,0,0))
    b=s.bounding_box()
    return s.translate((-b[0],-b[1],-b[2]))
