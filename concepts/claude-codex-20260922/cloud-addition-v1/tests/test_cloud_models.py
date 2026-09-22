import unittest,sys,io
from pathlib import Path
import numpy as np
import trimesh
from shapely.geometry import MultiPoint,Point
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cloud_models as m

class CloudAcceptance(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.designs=m.build_clouds()
 def test_four_requested_models(self):self.assertEqual(set(self.designs),{'A1','A2','A3','A4'})
 def test_height_and_parts(self):
  for k,d in self.designs.items():
   b=np.vstack([m.mesh(p.solid).bounds for p in d.parts])
   self.assertAlmostEqual(np.ptp(b,axis=0)[2],48,places=3)
   self.assertEqual(len(d.parts),4,k)
   self.assertEqual(sorted(p.color for p in d.parts),['black','black','orange','white'])
 def test_binary_meshes_closed_and_print_on_bed(self):
  for k,d in self.designs.items():
   for p in d.parts:
    s=m.portable_mesh(m.print_solid(p))
    q=trimesh.load_mesh(io.BytesIO(s.export(file_type='stl')),file_type='stl')
    self.assertTrue(q.is_watertight,(k,p.name));self.assertTrue(q.is_volume,(k,p.name))
    self.assertEqual(q.body_count,1,(k,p.name));self.assertAlmostEqual(q.bounds[0,2],0,places=5)
 def test_no_assembled_intersections(self):
  for k,d in self.designs.items():
   for i,p in enumerate(d.parts):
    for q in d.parts[i+1:]:self.assertLess((p.solid^q.solid).volume(),.01,(k,p.name,q.name))
 def test_binary_facets_have_positive_area(self):
  facet=np.dtype([('normal','<f4',(3,)),('vertices','<f4',(3,3)),('attribute','<u2')])
  for k,d in self.designs.items():
   for p in d.parts:
    for pose,solid in [('assembly',p.solid),('print',m.print_solid(p))]:
     data=m.portable_mesh(solid).export(file_type='stl')
     vertices=np.frombuffer(data,facet,offset=84)['vertices'].astype(np.float64)
     areas=np.linalg.norm(np.cross(vertices[:,1]-vertices[:,0],vertices[:,2]-vertices[:,0]),axis=1)/2
     self.assertTrue(np.all(areas>0),(k,p.name,pose,int(np.sum(areas==0))))
 def test_cloud_lowers_vertically_into_place(self):
  for k,d in self.designs.items():
   body=next(p.solid for p in d.parts if p.color=='orange')
   cloud=next(p.solid for p in d.parts if p.color=='white')
   for dz in (.1,.5,1,2,4,8,16,32,48):
    self.assertLess((body^cloud.translate((0,0,dz))).volume(),.01,(k,dz))
 def test_cloud_socket_has_no_thin_rear_shoulder_membrane(self):
  for key,z in [('A3',28.6),('A4',26.2)]:
   d=self.designs[key]
   cloud=next(p.solid for p in d.parts if p.name=='cloud')
   probe=m.md.Manifold.cube((.05,.05,.05),center=True).translate((26.17*d.scale,7.9*d.scale,(z-.8)*d.scale))
   self.assertLess((cloud^probe).volume(),1e-8,key)
 def test_four_flat_feet_and_center_of_mass(self):
  for k,d in self.designs.items():
   body=m.mesh(next(p.solid for p in d.parts if p.color=='orange'))
   floor=body.bounds[0,2]
   faces=body.faces[np.max(body.vertices[body.faces][:,:,2],axis=1)<floor+1e-4]
   contacts=trimesh.Trimesh(body.vertices,faces,process=True).split(only_watertight=False)
   self.assertEqual(len(contacts),4,k)
   xy=body.vertices[np.unique(faces)][:,:2]
   support=MultiPoint(xy).convex_hull
   solids=[m.mesh(p.solid) for p in d.parts]
   center=sum(s.center_mass*s.volume for s in solids)/sum(s.volume for s in solids)
   self.assertTrue(support.buffer(-1).contains(Point(center[:2])),(k,center.tolist()))
   self.assertGreater(support.area,150,k)
 def test_eyes_remain_printable_and_a4_sleepy(self):
  for k,d in self.designs.items():
   eyes=[m.mesh(p.solid) for p in d.parts if p.color=='black']
   self.assertEqual(len(eyes),2)
   self.assertTrue(all(min(e.extents)>1.15 for e in eyes),k)
   if k=='A4':self.assertGreater(eyes[0].extents[0]/eyes[0].extents[2],1.5)

if __name__=='__main__':unittest.main()
