"""A2/A3 closed-back cloud hats, millimetres, front -Y.

Printed v1 locator and eye dimensions are retained at 48 mm. Manufacturing
clearances remain in physical millimetres when regenerating another size.
"""
from pathlib import Path
from dataclasses import dataclass
from functools import lru_cache
import sys
import numpy as np
import trimesh
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'cloud-addition-v1'))
import cloud_models as old
base=old.base
md=base.md
mesh=base.mesh
COLORS=base.COLORS
Part=base.Part
KEY_CLEARANCE=.25
BODY_CLEARANCE=.22
SOCKET_WALL=1.7
PIN_DIAMETER=1.70
PIN_HOLE_DIAMETER=1.95
PIN_LENGTH=3.8
PIN_HOLE_DEPTH=2.2


def portable_mesh(solid):
    """Export a closed float32 mesh, stabilizing only rounding-collapsed facets.

    A Boolean can leave three nearly collinear vertices. Move one coordinate by
    a single float32 ULP, toward a positive facet with the original winding.
    The fallback rejects changes above 0.00001 mm or any topology/volume loss.
    """
    try:
        return old.portable_mesh(solid)
    except AssertionError:
        original=mesh(solid)
        assert original.is_volume and original.body_count==1
        verts=original.vertices.astype(np.float32)
        for _ in range(16):
            tri=verts[original.faces].astype(np.float64)
            normals=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
            collapsed=np.flatnonzero(np.linalg.norm(normals,axis=1)==0)
            if not len(collapsed):break
            face_id=int(collapsed[0]);ids=original.faces[face_id]
            raw=original.triangles[face_id]
            reference=np.cross(raw[1]-raw[0],raw[2]-raw[0])
            if np.linalg.norm(reference)<1e-20:
                reference=original.vertex_normals[ids].sum(axis=0)
            choices=[]
            for local,vertex in enumerate(ids):
                for axis in range(3):
                    for direction in [-np.inf,np.inf]:
                        value=np.nextafter(verts[vertex,axis],np.float32(direction))
                        test=tri[face_id].copy();test[local,axis]=value
                        normal=np.cross(test[1]-test[0],test[2]-test[0])
                        change=abs(float(value)-float(verts[vertex,axis]))
                        if change<=1e-5 and np.dot(normal,reference)>0:
                            choices.append((change,int(vertex),axis,value))
            assert choices,'Cannot stabilize STL facet within 0.00001 mm'
            _,vertex,axis,value=min(choices,key=lambda x:x[0]);verts[vertex,axis]=value
        result=trimesh.Trimesh(verts,original.faces,process=True)
        assert result.is_volume and result.body_count==1 and np.all(result.area_faces>0)
        assert np.max(np.abs(verts.astype(float)-original.vertices))<1e-5
        assert np.allclose(result.bounds,original.bounds,atol=1e-5)
        assert np.isclose(result.volume,original.volume,rtol=1e-5)
        return result

@dataclass
class RevisedDesign:
    name:str
    parts:list
    height_mm:float
    scale:float
    whole_cloud:object
    locator:object
    head_z:float
    pin_positions:list
    joint:dict


def print_solid(part):
    solid=part.solid
    if part.orientation in ('back','front_seam'):solid=solid.rotate((-90,0,0))
    elif part.orientation in ('back_seam','pin_axis'):solid=solid.rotate((90,0,0))
    elif part.orientation!='upright':raise ValueError(part.orientation)
    box=solid.bounding_box()
    return solid.translate((-box[0],-box[1],-box[2]))


def down_sweep(solid,distance=160):
    return md.Manifold.batch_hull([solid,solid.translate((0,0,-distance))])


def cylinder_y(diameter,length,at):
    return md.Manifold.cylinder(length,diameter/2,diameter/2,48,center=True).rotate((90,0,0)).translate(at)


def fill_internal_tangencies(solid):
    """Fill only tiny enclosed negative tetrahedra left at boolean tangencies.

    An open locator recess belongs to the positive connected surface and is
    retained. A positive detached solid or >0.001 mm^3 void fails explicitly.
    """
    components=solid.decompose()
    positive=[s for s in components if s.volume()>0]
    negative=[s for s in components if s.volume()<=0]
    filled=-sum(s.volume() for s in negative)
    assert len(positive)==1 and filled<.001, filled
    return positive[0],filled


@lru_cache(maxsize=8)
def build_model(key,height_mm=48):
    if key not in ('A2','A3'):raise ValueError('This physical refinement covers A2 and A3')
    if not 40<=height_mm<=150:raise ValueError('Supported height 40–150 mm')
    legacy=old.build_clouds(height_mm)[key]
    scale=legacy.scale
    zscale={'A2':.72,'A3':1}[key]
    hz=45*zscale
    transform=lambda solid:solid.translate((0,0,-.8)).scale((scale,)*3)
    bare_master=base.standing_clawd().scale((1,1,zscale)).trim_by_plane((0,0,1),.8)
    # Keep the rear rounding instead of flattening Y=11.7 as in v1.
    peg_master=base.rounded((18,10,4),1,(0,0,hz+1))
    master_parts=[Part('clawd','orange',bare_master+peg_master,'upright',True)]
    base.add_eyes(master_parts,0,[(-11,33*zscale),(11,33*zscale)],-12.5,5.5)
    parts=[Part(p.name,p.color,transform(p.solid),p.orientation,p.support) for p in master_parts]
    bare=transform(bare_master)
    locator=transform(peg_master)
    head_z=(hz-.8)*scale
    # No posterior plane cut. Existing cloud identity/front silhouette retained.
    outer=transform(old.smooth_cloud(old.LOBES[key],step=.28,blend=2.1))
    # Sampling resolution may shift the top by microns; keep exact requested
    # height without scaling the already printed body or connector.
    outer=outer.scale((1,1,height_mm/outer.bounding_box()[5]))
    # A rounded internal boss guarantees material around the blind key pocket,
    # including where the original lobes did not enclose the back of the key.
    boss=locator.minkowski_sum(md.Manifold.sphere(KEY_CLEARANCE+SOCKET_WALL,32)).hull()
    clearance=down_sweep(bare).minkowski_sum(md.Manifold.sphere(BODY_CLEARANCE,32)).hull()
    key_pocket=down_sweep(locator).minkowski_sum(md.Manifold.sphere(KEY_CLEARANCE,32)).hull()
    whole=(outer+boss)-clearance-key_pocket
    whole,filled_void=fill_internal_tangencies(whole)
    # Two hidden alignment pins keep the front/back seam registered. Filament
    # segments 1.75 x 3.8 mm can replace the included 1.70 mm printed pins.
    peg_bounds=np.array(locator.bounding_box()).reshape(2,3)
    pin_z=float(peg_bounds[1,2]+KEY_CLEARANCE+SOCKET_WALL+3)
    pin_x=max(4.,float(peg_bounds[1,0])*.72)
    positions=[(-pin_x,0.,pin_z),(pin_x,0.,pin_z)]
    drills=base.union(cylinder_y(PIN_HOLE_DIAMETER,2*PIN_HOLE_DEPTH,p) for p in positions)
    front=whole.trim_by_plane((0,-1,0),0)-drills
    back=whole.trim_by_plane((0,1,0),0)-drills
    parts.extend([Part('cloud_front','white',front,'front_seam',False),Part('cloud_back','white',back,'back_seam',False)])
    for i,p in enumerate(positions,1):parts.append(Part(f'cloud_pin_{i}','white',cylinder_y(PIN_DIAMETER,PIN_LENGTH,p),'pin_axis',False))
    spec={'key_width_mm':float(peg_bounds[1,0]-peg_bounds[0,0]),'key_depth_mm':float(peg_bounds[1,1]-peg_bounds[0,1]),'key_exposed_height_mm':float(peg_bounds[1,2]-head_z),'clearance_per_side_mm':KEY_CLEARANCE,'roof_clearance_mm':KEY_CLEARANCE,'boss_shell_mm':SOCKET_WALL,'body_clearance_mm':BODY_CLEARANCE,'socket_opening':'bottom only; closed back and roof','pin_diameter_mm':PIN_DIAMETER,'pin_hole_diameter_mm':PIN_HOLE_DIAMETER,'pin_length_mm':PIN_LENGTH,'pin_hole_depth_per_half_mm':PIN_HOLE_DEPTH,'filled_numerical_internal_void_mm3':filled_void,'physical_fit_status':'NOT_TESTED'}
    return RevisedDesign(key,parts,height_mm,scale,whole,locator,head_z,positions,spec)


def fit_coupon(key,clearance=.25):
    """Actual 48 mm locator and a small blind female test socket; no whole print."""
    design=build_model(key)
    peg=design.locator.translate((0,0,-design.head_z))
    platform=base.rounded((design.joint['key_width_mm']+7,design.joint['key_depth_mm']+7,2),.6,(0,0,-1))
    male=(peg+platform).trim_by_plane((0,0,1),-2)
    cavity=down_sweep(peg).minkowski_sum(md.Manifold.sphere(clearance,32)).hull()
    # A simple external box makes the small coupon robust in float32 STL.
    # Its internal socket is the same physical swept locator as the cloud.
    top=peg.bounding_box()[5]+clearance+SOCKET_WALL
    width=design.joint['key_width_mm']+2*(clearance+SOCKET_WALL)
    depth=design.joint['key_depth_mm']+2*(clearance+SOCKET_WALL)
    outer=md.Manifold.cube((width,depth,top-BODY_CLEARANCE)).translate((-width/2,-depth/2,BODY_CLEARANCE))
    female=outer-cavity
    female,_=fill_internal_tangencies(female)
    # Remove a nearly collinear Boolean facet before float32 serialization.
    # Coupon tessellation tolerance is 0.01 mm; full cloud sockets are unchanged.
    female=female.simplify(.01)
    female,_=fill_internal_tangencies(female)
    # The female socket prints opening-up, so its pocket does not need support.
    return [Part(f'{key}_key_test','orange',male,'upright',False),Part(f'{key}_socket_{clearance:.2f}','white',female.rotate((180,0,0)),'upright',False)]
