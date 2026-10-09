"""524 sculpture, from the original vector silhouettes; units mm.
A continuous full-volume double-surface body, integrated plinth and dots.
The depth, back and surface are proposed modelling decisions from Concept 01.
"""
import json
from functools import lru_cache
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
import manifold3d as m
import trimesh

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parent.parent/'exports/editable-outlines.json'
STEP=.18
BORDER=8.


def as_trimesh(solid):
    a=solid.to_mesh()
    return trimesh.Trimesh(np.asarray(a.vert_properties)[:,:3],np.asarray(a.tri_verts),process=True)


def mask_from(polygons,shape):
    im=Image.new('L',(shape[1],shape[0]))
    d=ImageDraw.Draw(im)
    for p in polygons:
        d.polygon([((x+75+BORDER)/STEP,(z+BORDER)/STEP) for x,z in p],fill=255)
    return np.asarray(im)>0


def smoothstep(x):
    x=np.clip(x,0,1)
    return x*x*(3-2*x)


@lru_cache(maxsize=1)
def build_statue():
    raw=json.loads(SOURCE.read_text())
    orig_h=max(v[1] for p in raw['body'] for v in p)
    polygons={k:[np.asarray(p)*[1.5,153/orig_h]+[-75,0] for p in ps] for k,ps in raw.items()}
    shape=(int((153+2*BORDER)/STEP)+1,int((150+2*BORDER)/STEP)+1)
    masks={k:mask_from(p,shape) for k,p in polygons.items()}
    distance=ndimage.distance_transform_edt(masks['body'])*STEP
    # A gently flattened face and rounder back, rather than an extruded plaque.
    signed_distance=distance-ndimage.distance_transform_edt(~masks['body'])*STEP
    smooth_distance=np.maximum(0,ndimage.gaussian_filter(signed_distance,1.5/STEP))
    # Smooth the medial ridges of an EDT while retaining the traced silhouette.
    profile=np.sqrt(1-np.exp(-smooth_distance/10.5))
    profile/=profile.max()
    half=.8+38.8*profile
    eye_d=ndimage.distance_transform_edt(masks['eyes'])*STEP
    dome=3.5*smoothstep(eye_d/4.5)
    digit_d=ndimage.distance_transform_edt(masks['digits'])*STEP
    mouth_d=ndimage.distance_transform_edt(masks['mouth'])*STEP
    digits=1.75*smoothstep(digit_d/.7)
    mouth=2.5*smoothstep(mouth_d/.9)
    front=ndimage.gaussian_filter(half+dome-digits-mouth,.18/STEP)
    rear=ndimage.gaussian_filter(.8+41.1*profile,.18/STEP)
    def sample(field,x,z):
        return ndimage.map_coordinates(field,[(z+BORDER)/STEP,(x+75+BORDER)/STEP],order=1,mode='nearest')
    raw_body=m.CrossSection(polygons['body']).extrude(2).refine_to_length(.64)
    def warp(v):
        v=np.asarray(v)
        t=v[:,2]/2
        f=sample(front,v[:,0],v[:,1]);b=sample(rear,v[:,0],v[:,1])
        return np.column_stack([v[:,0],(1-t)*b-t*f,v[:,1]+15.0])
    body=raw_body.warp_batch(warp).simplify(.035)
    # Normalize the total depth to the selected 85mm design target.
    bounds=body.bounding_box(); depth=bounds[4]-bounds[1]
    body=body.translate([0,-(bounds[1]+bounds[4])/2,0]).scale([1,85/depth,1])
    cs=m.CrossSection.square([165,105],center=True).offset(5,circular_segments=48)
    base=cs.extrude(17)+cs.extrude(1,scale_top=[173/175,113/115]).translate([0,0,17])
    dots=[m.Manifold.sphere(1,48).scale([6,5,3.8]).translate([56,-47,19.6]),
          m.Manifold.sphere(1,40).scale([4.4,3.8,3.0]).translate([71,-48,19.0])]
    statue=m.Manifold.batch_boolean([body,base,*dots],m.OpType.Add).simplify(.025)
    result={'statue':statue,'body':body,'base':base,'dots':dots,
            'face_probe':{'digit_components':ndimage.label(masks['digits'])[1],
              'digit_recess_measured':float(digits.max()),
              'mouth_recess_measured':float(mouth.max()),
              'eye_dome_measured':float(dome.max())}}
    return result


def main():
    out=ROOT/'output';out.mkdir(exist_ok=True)
    result=build_statue()
    mesh=as_trimesh(result['statue'])
    mesh.export(out/'524-sculpture-with-plinth.stl')
    as_trimesh(result['body']).export(out/'body-review-only.stl')
    report={'dimensions_mm':mesh.extents.tolist(),'bounds_mm':mesh.bounds.tolist(),
            'volume_mm3':float(mesh.volume),'faces':len(mesh.faces),
            'watertight':bool(mesh.is_watertight),'winding_consistent':bool(mesh.is_winding_consistent),
            'components':len(mesh.split()),'face_probe':result['face_probe'],
            'material_lot':'FIL-016','ams_slot_user_reported':'A3',
            'source':'original-524 silhouette traced in editable-outlines.json',
            'depth_design':'continuous front/back inflation, domed face and incised digits/mouth',
            'body_embedded_in_plinth_mm':3,'sliced':False,'printed':False}
    (out/'mesh-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
