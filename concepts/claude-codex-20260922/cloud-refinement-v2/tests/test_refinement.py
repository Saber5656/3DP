import sys,unittest,io
from pathlib import Path
import numpy as np
import trimesh
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import refined_models as m


def ray_wall(cloud,origin,direction):
    loc,_,_=m.mesh(cloud).ray.intersects_location([origin],[direction],multiple_hits=True)
    distances=sorted(float(np.dot(p-origin,direction)) for p in loc if np.dot(p-origin,direction)>1e-5)
    return distances

class RefinementAcceptance(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.models={k:m.build_model(k) for k in ['A2','A3']}
 def test_round_cloud_rear_has_no_large_cut_face(self):
  for key,d in self.models.items():
   q=m.mesh(d.whole_cloud);rear=q.bounds[1,1]
   on_plane=np.all(np.abs(q.triangles[:,:,1]-rear)<1e-4,axis=1)
   self.assertLess(float(q.area_faces[on_plane].sum()/q.area),.015,key)
 def test_key_has_closed_sides_and_roof(self):
  for key,d in self.models.items():
   # Probe the existing printed locator, not a self-declared socket dimension.
   origin=np.array([0.,0.,d.head_z+1.5*d.scale])
   for direction in [np.array(x,dtype=float) for x in [(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1)]]:
    hits=ray_wall(d.whole_cloud,origin,direction)
    self.assertGreaterEqual(len(hits),2,(key,direction.tolist(),hits))
    self.assertGreaterEqual(hits[1]-hits[0],1.45,(key,direction.tolist(),hits))
 def test_complete_key_has_clearance(self):
  for key,d in self.models.items():
   q=d.locator.minkowski_sum(m.base.md.Manifold.sphere(.20,24))
   self.assertLess((q^d.whole_cloud).volume(),.001,key)
 def test_key_restricts_sideways_movement(self):
  for key,d in self.models.items():
   for delta in [(1,0,0),(-1,0,0),(0,1,0),(0,-1,0)]:
    self.assertGreater((d.locator.translate(delta)^d.whole_cloud).volume(),.01,(key,delta))
 def test_printed_body_is_still_compatible(self):
  for key,d in self.models.items():
   legacy=m.old.build_clouds(48)[key]
   body=next(p.solid for p in legacy.parts if p.name=='clawd')
   for dz in np.linspace(0,48,97):
    self.assertLess((body^d.whole_cloud.translate((0,0,float(dz)))).volume(),.001,(key,dz))
 def test_new_body_seats_without_intersection(self):
  for key,d in self.models.items():
   body=next(p.solid for p in d.parts if p.name=='clawd')
   for dz in np.linspace(0,48,97):
    self.assertLess((body^d.whole_cloud.translate((0,0,float(dz)))).volume(),.001,(key,dz))
 def test_split_cloud_prints_from_hidden_seam(self):
  for key,d in self.models.items():
   halves=[p for p in d.parts if p.name in ['cloud_front','cloud_back']]
   self.assertEqual(len(halves),2,key)
   for p in halves:
    q=m.mesh(m.print_solid(p));self.assertAlmostEqual(q.bounds[0,2],0,places=5)
    plane=np.max(q.triangles[:,:,2],axis=1)<1e-4
    self.assertGreater(q.area_faces[plane].sum(),150,(key,p.name))
 def test_actual_48mm_mesh_parts_are_closed(self):
  for key,d in self.models.items():
   bounds=np.vstack([m.mesh(p.solid).bounds for p in d.parts])
   self.assertAlmostEqual(np.ptp(bounds,axis=0)[2],48,places=4)
   for p in d.parts:
    q=m.portable_mesh(m.print_solid(p));r=trimesh.load_mesh(io.BytesIO(q.export(file_type='stl')),file_type='stl')
    self.assertTrue(r.is_watertight and r.is_volume,(key,p.name));self.assertEqual(r.body_count,1)
    self.assertTrue(np.all(r.area_faces>0),(key,p.name))

 def test_fit_coupons_export_as_closed_single_parts(self):
  for key in self.models:
   for clearance in [.20,.25,.30]:
    for part in m.fit_coupon(key,clearance):
     q=m.portable_mesh(m.print_solid(part))
     self.assertTrue(q.is_watertight and q.is_volume,(key,part.name))
     self.assertEqual(q.body_count,1,(key,part.name))
 def test_optional_onepiece_survives_stl_roundtrip(self):
  for key,d in self.models.items():
   part=m.Part('cloud','white',d.whole_cloud,'upright',True)
   q=m.portable_mesh(m.print_solid(part))
   r=trimesh.load_mesh(io.BytesIO(q.export(file_type='stl')),file_type='stl')
   self.assertTrue(r.is_volume and r.body_count==1 and np.all(r.area_faces>0),key)
 def test_alignment_pins_are_hidden_and_clear_of_shells(self):
  for key,d in self.models.items():
   for position in d.pin_positions:
    protected=m.cylinder_y(m.PIN_HOLE_DIAMETER+2.4,2*(m.PIN_HOLE_DEPTH+1.2),position)
    self.assertLess((protected-d.whole_cloud).volume(),.001,(key,position))
   for i,p in enumerate(d.parts):
    for q in d.parts[i+1:]:
     self.assertLess((p.solid^q.solid).volume(),.001,(key,p.name,q.name))
 def test_four_feet_still_support_rounded_cloud(self):
  from shapely.geometry import MultiPoint,Point
  for key,d in self.models.items():
   body=m.mesh(d.parts[0].solid)
   faces=body.faces[np.max(body.triangles[:,:,2],axis=1)<1e-4]
   feet=trimesh.Trimesh(body.vertices,faces,process=True).split(only_watertight=False)
   self.assertEqual(len(feet),4,key)
   support=MultiPoint(body.vertices[np.unique(faces)][:,:2]).convex_hull
   solids=[m.mesh(p.solid) for p in d.parts]
   center=sum(q.volume*q.center_mass for q in solids)/sum(q.volume for q in solids)
   self.assertTrue(support.buffer(-1).contains(Point(center[:2])),(key,center.tolist()))

if __name__=='__main__':unittest.main()
