"""Export the 5 mm outside-diameter trial and validate the exported geometry."""
from pathlib import Path
from dataclasses import asdict
import hashlib, json, zipfile
import xml.etree.ElementTree as ET
import cadquery as cq
import trimesh
import numpy as np
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from body_v3 import BodyV3, body_v3

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output/body-v3'; OUT.mkdir(parents=True,exist_ok=True)
D=BodyV3()
REPORT={'parameters_mm':asdict(D),'stage':'complete mechanical prototype; rear physical fit and seal untested','parts':{}}
meshes=[]
for name,shape in [('kirby_body_v3_5mm_OD',body_v3(D))]:
    stl=OUT/f'{name}.stl'; step=OUT/f'{name}.step'
    cq.exporters.export(shape,str(stl),tolerance=.02,angularTolerance=.12)
    cq.exporters.export(shape,str(step))
    step.write_text('\n'.join(x.rstrip() for x in step.read_text().splitlines())+'\n')
    mesh=trimesh.load_mesh(stl,process=True)
    back=cq.importers.importStep(str(step)).val()
    box=Bnd_Box(); BRepBndLib.AddOptimal_s(shape.val().wrapped,box,False,False)
    b=np.array(box.Get()); ext=b[3:]-b[:3]
    r={'cad_valid':shape.val().isValid(),'solids':len(shape.solids().vals()),
       'stl_watertight':mesh.is_watertight,'stl_consistent_winding':mesh.is_winding_consistent,
       'stl_bodies':int(mesh.body_count),'stl_euler':int(mesh.euler_number),
       'stl_volume_mm3':float(mesh.volume),'cad_volume_mm3':shape.val().Volume(),
       'step_valid':back.isValid(),'step_volume_difference_mm3':abs(back.Volume()-shape.val().Volume()),
       'extent_mm':mesh.extents.tolist(),'max_extent_error_mm':float(abs(mesh.extents-ext).max()),
       'degenerate_triangles':int((mesh.area_faces<1e-10).sum()),'triangles':len(mesh.faces),
       'stl_sha256':hashlib.sha256(stl.read_bytes()).hexdigest()}
    assert r['cad_valid'] and r['step_valid']
    assert r['solids']==r['stl_bodies']==1
    assert r['stl_watertight'] and r['stl_consistent_winding']
    assert r['stl_volume_mm3']>0 and r['stl_euler']==0 and r['degenerate_triangles']==0
    assert r['max_extent_error_mm']<.04 and r['step_volume_difference_mm3']<.02
    REPORT['parts'][name]=r
    meshes.append((name,mesh))
    print(name,json.dumps(r),flush=True)

ns='http://schemas.microsoft.com/3dmanufacturing/core/2015/02'
model=ET.Element('model',unit='millimeter',xmlns=ns)
ET.SubElement(model,'metadata',name='Title').text='Kirby body v3 / 5 mm OUTSIDE diameter / BLACK PLA'
ET.SubElement(model,'metadata',name='Description').text='Geometry only. Rear insert OD5 ID3 length8 mm. Use existing5mmhole. Physical fit, retention, restricted flow need trial.'
resources=ET.SubElement(model,'resources'); build=ET.SubElement(model,'build')
for i,(name,mesh) in enumerate(meshes,1):
    obj=ET.SubElement(resources,'object',id=str(i),type='model',name=name)
    m=ET.SubElement(obj,'mesh'); vv=ET.SubElement(m,'vertices'); tt=ET.SubElement(m,'triangles')
    for point in mesh.vertices:
        ET.SubElement(vv,'vertex',**dict(zip(('x','y','z'),(f'{v:.8f}' for v in point))))
    for face in mesh.faces:
        ET.SubElement(tt,'triangle',**dict(zip(('v1','v2','v3'),map(str,face))))
    ET.SubElement(build,'item',objectid=str(i),transform=f'1 0 0 0 1 0 0 0 1 {90+65*(i-1)} 128 0')
with zipfile.ZipFile(OUT/'kirby_body_v3_5mm_OD.3mf','w',zipfile.ZIP_DEFLATED) as z:
    z.writestr('[Content_Types].xml','<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
    z.writestr('_rels/.rels','<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
    z.writestr('3D/3dmodel.model',ET.tostring(model,encoding='utf-8',xml_declaration=True))
with zipfile.ZipFile(OUT/'kirby_body_v3_5mm_OD.3mf') as z:
    assert z.testzip() is None
    xml=ET.fromstring(z.read('3D/3dmodel.model')); n={'m':ns}
    assert xml.attrib['unit']=='millimeter'
    for m in xml.findall('m:resources/m:object/m:mesh',n):
        v=[[float(x.attrib[k]) for k in ('x','y','z')] for x in m.find('m:vertices',n)]
        f=[[int(x.attrib[k]) for k in ('v1','v2','v3')] for x in m.find('m:triangles',n)]
        roundtrip=trimesh.Trimesh(vertices=v,faces=f,process=False)
        assert roundtrip.is_watertight and roundtrip.body_count==1
REPORT['assembly_3mf']={'parts':1,'watertight_without_repair':True,'units':'mm','printer_profile':False}
REPORT['limitations']=['5 mm is the maximum insert OUTSIDE diameter, not the bore.',
 'Bore is 3 mm. Debris above 3 mm cannot pass and airflow is restricted.',
 'Smooth friction-fit prototype; no positive mechanical lock. Rear fit, retention and seal untested.',
 'Do not enlarge the existing 5 mm rear hole. Do not use V2 28 mm files.',
 'Printed dimensions and physical suction are unverified. Support the vacuum independently.']
(OUT/'geometry-report.json').write_text(json.dumps(REPORT,indent=2,ensure_ascii=False)+'\n')
