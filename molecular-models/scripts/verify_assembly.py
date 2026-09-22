"""Conservative continuous guest insertion proof, plus sampled frame closure."""
import json
from pathlib import Path
import numpy as np
import trimesh


def projected_triangle_distances(point, triangles):
    """Exact 2D point-to-triangle distances; includes degenerate projections."""
    t=np.asarray(triangles);a=t;b=np.roll(t,-1,axis=1);v=b-a;x=np.asarray(point)-a
    fraction=np.clip(np.einsum('ijk,ijk->ij',x,v)/np.maximum(np.einsum('ijk,ijk->ij',v,v),1e-20),0,1)
    distances=np.linalg.norm(x-fraction[:,:,None]*v,axis=2).min(1)
    cross=v[:,:,0]*x[:,:,1]-v[:,:,1]*x[:,:,0]
    area=(t[:,1,0]-t[:,0,0])*(t[:,2,1]-t[:,0,1])-(t[:,1,1]-t[:,0,1])*(t[:,2,0]-t[:,0,0])
    inside=((cross>=-1e-10).all(1)|(cross<=1e-10).all(1))&(abs(area)>1e-10)
    distances[inside]=0
    return distances


def insertion_distance_bound(mesh, centre):
    """Lower bound along centre + (0,0,t), t >= 0: insert FROM ABOVE to centre.

    The guest stops at centre and never travels below it. Reversing this same
    ray describes removal upward; insertion from below is not checked.

    Triangles wholly below the final centre cannot get closer as the centre rises.
    For remaining triangles, horizontal separation bounds distance at every height.
    This bound can be conservative, but cannot overlook an overhead obstacle.
    """
    centre=np.asarray(centre)
    final_distance=float(trimesh.proximity.closest_point_naive(mesh,[centre])[1][0])
    upper=mesh.triangles[mesh.triangles[:,:,2].max(1)>centre[2]]
    if len(upper)==0:return final_distance
    horizontal=projected_triangle_distances(centre[:2],upper[:,:,:2]).min()
    return float(min(final_distance,horizontal))


def verify(out):
    report=json.loads((out/'validation.json').read_text())['models']['mof5']
    guest=report['guest'];centre=np.array(guest['center_mm']);radius=guest['guest_outer_radius_mm']
    lower=trimesh.load_mesh(out/'mof5_lower.stl');upper=trimesh.load_mesh(out/'mof5_upper.stl')
    lower_margin=insertion_distance_bound(lower,centre)-radius
    # Every upper-frame vertex is above the guest centre. Raising the upper
    # frame therefore increases distance from every point of it to the centre.
    assert upper.bounds[0,2]>centre[2]
    upper_margin=float(trimesh.proximity.closest_point_naive(upper,[centre])[1][0])-radius
    closure=[]
    for dz in [0,.5,1,2,3,4,6,8,16,32,64,128]:
        moved=upper.copy();moved.apply_translation([0,0,dz])
        overlap=trimesh.boolean.intersection([lower,moved],engine='manifold')
        volume=0.0 if overlap.is_empty else float(abs(overlap.volume))
        closure.append({'upper_lift_mm':dz,'intersection_volume_mm3':volume})
    assert min(lower_margin,upper_margin)>1
    assert max(x['intersection_volume_mm3'] for x in closure)<.001
    result=dict(stage='Rigid geometric verification only; physical assembly NOT_RUN',
        guest_insertion_continuous_clearance_lower_bound_mm=lower_margin,
        upper_over_guest_continuous_clearance_lower_bound_mm=upper_margin,
        method='Bounding sphere containing the entire guest; monotonic vertical distance and exact triangle projections',
        frame_closure=closure,frame_closure_scope='Sampled offsets only; not a continuous proof or fit test',
        assembly_path='Insert CH4 vertically into the first lower pore at x=y=-33.26278984 mm, then lower the upper frame vertically.')
    (out/'assembly-validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':verify(Path(__file__).resolve().parents[1]/'output')
