"""Reuse the printed Wood sculpture's body and surface field at 40 mm height."""
import json
from functools import lru_cache
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
import manifold3d as m
import trimesh

SOURCE = Path(__file__).parent / 'source' / 'wood-reference'
RATIO = 40 / 153


@lru_cache(maxsize=1)
def wood_body():
    raw = json.loads((SOURCE / 'editable-outlines.json').read_text())
    orig_h = max(v[1] for p in raw['body'] for v in p)
    polygons = {k: [np.asarray(p)*[1.5, 153/orig_h]+[-75, 0] for p in ps]
                for k, ps in raw.items()}
    step, border = .18, 8.
    shape = (int((153+2*border)/step)+1, int((150+2*border)/step)+1)
    masks = {}
    for name, polys in polygons.items():
        image = Image.new('L', (shape[1], shape[0]))
        draw = ImageDraw.Draw(image)
        for p in polys:
            draw.polygon([((x+75+border)/step, (z+border)/step) for x,z in p], fill=255)
        masks[name] = np.asarray(image) > 0
    signed = (ndimage.distance_transform_edt(masks['body'])-
              ndimage.distance_transform_edt(~masks['body']))*step
    distance = np.maximum(0, ndimage.gaussian_filter(signed, 1.5/step))
    profile = np.sqrt(1-np.exp(-distance/10.5))
    profile /= profile.max()
    def smooth(x):
        x = np.clip(x, 0, 1)
        return x*x*(3-2*x)
    dome = 3.5*smooth(ndimage.distance_transform_edt(masks['eyes'])*step/4.5)
    digits = 1.75*smooth(ndimage.distance_transform_edt(masks['digits'])*step/.7)
    mouth = 2.5*smooth(ndimage.distance_transform_edt(masks['mouth'])*step/.9)
    front = ndimage.gaussian_filter(.8+38.8*profile+dome-digits-mouth, .18/step)
    rear = ndimage.gaussian_filter(.8+41.1*profile, .18/step)
    def sample(field, x, z):
        x, z = np.broadcast_arrays(np.asarray(x), np.asarray(z))
        a = ndimage.map_coordinates(field, [(z.ravel()+border)/step,
                                            (x.ravel()+75+border)/step], order=1, mode='nearest')
        return a.reshape(x.shape)
    # Repeat the original meshing only to recover its exact Y normalization.
    # The delivered body itself is loaded from the retained original STL.
    def warp(v):
        x,z,t = np.asarray(v).T
        t = t/2
        return np.column_stack([x, (1-t)*sample(rear,x,z)-t*sample(front,x,z), z+15])
    original = m.CrossSection(polygons['body']).extrude(2).refine_to_length(.64).warp_batch(warp).simplify(.035)
    bounds = original.bounding_box()
    center = (bounds[1]+bounds[4])/2
    depth_scale = 85/(bounds[4]-bounds[1])
    mesh = trimesh.load_mesh(SOURCE/'body-review-only.stl')
    body = m.Manifold(m.Mesh64(mesh.vertices, np.asarray(mesh.faces, dtype=np.uint64)))
    body = body.translate([0,0,-15]).scale([RATIO]*3)
    def surface(x,z):
        # Positive distances along -Y (front) and +Y (rear).
        f = (sample(front,np.asarray(x)/RATIO,np.asarray(z)/RATIO)+center)*depth_scale*RATIO
        b = (sample(rear,np.asarray(x)/RATIO,np.asarray(z)/RATIO)-center)*depth_scale*RATIO
        return f,b
    return body, {k: [p*RATIO for p in ps] for k,ps in polygons.items()}, surface
