"""Export millimetre CAD/STL/3MF artifacts and verify their round trips."""
from dataclasses import asdict
from pathlib import Path
import hashlib
import importlib.metadata
import json
import zipfile
import xml.etree.ElementTree as ET
import cadquery as cq
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
import numpy as np
import trimesh
from adapter import Dimensions, fit_coupon, adapter_body, rear_gasket, coupon_print_orientation

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output'; OUT.mkdir(exist_ok=True)
D=Dimensions().validate()
REPORT={'units':'mm','stage':'geometry validation; fit_30 tightness accepted by user; rear adapter remains preliminary',
        'measured':json.loads((ROOT/'design/user-measurements.json').read_text()),
        'parameters':asdict(D),'versions':{x:importlib.metadata.version(x) for x in ('cadquery','trimesh','numpy')},'parts':{}}

def export_part(name,shape):
    stl=OUT/f'{name}.stl'; step=OUT/f'{name}.step'
    cq.exporters.export(shape,str(stl),tolerance=.015,angularTolerance=.08)
    cq.exporters.export(shape,str(step))
    step.write_text('\n'.join(line.rstrip() for line in step.read_text().splitlines())+'\n')
    mesh=trimesh.load_mesh(stl,process=True)
    solid=shape.val(); reread=cq.importers.importStep(str(step)).val()
    bb=Bnd_Box(); BRepBndLib.AddOptimal_s(solid.wrapped,bb,False,False)
    bounds=np.array(bb.Get()); expected=bounds[3:]-bounds[:3]
    report={
        'cad_valid':bool(solid.isValid()),'cad_solid_count':len(shape.solids().vals()),
        'step_roundtrip_valid':bool(reread.isValid()),'step_volume_error_mm3':abs(reread.Volume()-solid.Volume()),
        'watertight':bool(mesh.is_watertight),'consistent_winding':bool(mesh.is_winding_consistent),
        'positive_volume':bool(mesh.volume>0),'connected_bodies':int(mesh.body_count),
        'euler_number':int(mesh.euler_number),'degenerate_faces':int((mesh.area_faces<1e-10).sum()),
        'extent_mm':mesh.extents.tolist(),'cad_extent_mm':expected.tolist(),
        'max_extent_error_mm':float(np.max(np.abs(mesh.extents-expected))),
        'volume_mm3':float(mesh.volume),'triangles':len(mesh.faces),
        'stl_sha256':hashlib.sha256(stl.read_bytes()).hexdigest()}
    assert report['cad_valid'] and report['step_roundtrip_valid']
    assert report['cad_solid_count']==report['connected_bodies']==1
    assert report['watertight'] and report['consistent_winding'] and report['positive_volume']
    assert report['euler_number']==0 and report['degenerate_faces']==0
    assert report['max_extent_error_mm']<.03
    assert report['step_volume_error_mm3']<.01
    REPORT['parts'][name]=report
    return mesh

coupons=[]
for index,c in enumerate((.15,.30,.45)):
    code=f'{round(c*100):02d}'
    part=coupon_print_orientation(fit_coupon(D,c))
    # Shallow, readable identification on the exposed top of the grip.
    letters=cq.Workplane('XY',origin=(0,8.3,2.55)).text(code,2.4,.60,font='Arial',combine=True)
    part=part.cut(letters).clean()
    export_part(f'fit_{code}',part)
    coupons.append(part.translate((index*55,0,0)).val())
# Use welded, verified STL vertices for interoperable 3MF. Direct CAD tessellation
# contains per-face duplicate vertices which the Bambu 3MF importer does not weld.
ns_uri='http://schemas.microsoft.com/3dmanufacturing/core/2015/02'
model=ET.Element('model',unit='millimeter',xmlns=ns_uri)
ET.SubElement(model,'metadata',name='Title').text='Kirby fit coupons: 15, 30, 45'
ET.SubElement(model,'metadata',name='Description').text='Geometry only. Offsets per side 0.15, 0.30, 0.45 mm. User accepted fit_30 tightness; depth clarification pending.'
resources=ET.SubElement(model,'resources'); build=ET.SubElement(model,'build')
mesh_counts=[]
for index,code in enumerate(('15','30','45'),start=1):
    mesh=trimesh.load_mesh(OUT/f'fit_{code}.stl',process=True)
    mesh.apply_translation(((index-1)*55,0,0))
    obj=ET.SubElement(resources,'object',id=str(index),type='model',name=f'fit_{code}')
    xm=ET.SubElement(obj,'mesh'); vertices=ET.SubElement(xm,'vertices'); triangles=ET.SubElement(xm,'triangles')
    for point in mesh.vertices: ET.SubElement(vertices,'vertex',**dict(zip(('x','y','z'),(f'{n:.8f}' for n in point))))
    for tri in mesh.faces: ET.SubElement(triangles,'triangle',**dict(zip(('v1','v2','v3'),map(str,tri))))
    ET.SubElement(build,'item',objectid=str(index))
    mesh_counts.append(len(mesh.faces))
content='<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>'
rels='<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>'
with zipfile.ZipFile(OUT/'fit_set.3mf','w',zipfile.ZIP_DEFLATED) as z:
    z.writestr('[Content_Types].xml',content); z.writestr('_rels/.rels',rels)
    z.writestr('3D/3dmodel.model',ET.tostring(model,encoding='utf-8',xml_declaration=True))
with zipfile.ZipFile(OUT/'fit_set.3mf') as z:
    xml=ET.fromstring(z.read('3D/3dmodel.model')); ns={'m':ns_uri}
    assert xml.attrib['unit']=='millimeter'
    meshes=xml.findall('m:resources/m:object/m:mesh',ns)
    assert len(meshes)==3
    for xm in meshes:
        verts=[[float(v.attrib[k]) for k in ('x','y','z')] for v in xm.find('m:vertices',ns)]
        tris=[[int(t.attrib[k]) for k in ('v1','v2','v3')] for t in xm.find('m:triangles',ns)]
        reread=trimesh.Trimesh(vertices=verts,faces=tris,process=False)
        assert reread.is_watertight and reread.body_count==1
    REPORT['fit_set_3mf']={'unit':'millimeter','mesh_parts':3,'watertight_without_repair':True,'printer_profile_included':False}

body=adapter_body(D)
export_part('draft_rear_adapter',body)
export_part('draft_rear_gasket_TPU',rear_gasket(D))
checks=[]
for z in np.arange(.25,58,.5):
    wires=body.section(float(z)).wires().vals()
    assert len(wires)==2,(z,len(wires))
    checks.append({'z_mm':float(z),'minimum_in_plane_wall_mm':float(wires[0].distance(wires[1]))})
REPORT['section_wall_checks']=checks
REPORT['minimum_sampled_wall_mm']=min(x['minimum_in_plane_wall_mm'] for x in checks)
assert REPORT['minimum_sampled_wall_mm']>.99
# A cutaway is for visual inspection only and is never delivered as printable geometry.
cut=body.cut(cq.Workplane('XY').box(120,100,150).translate((0,-50,50)))
cq.exporters.export(cut,str(OUT/'inspection_cutaway.stl'),tolerance=.03,angularTolerance=.12)
REPORT['limitations']=[
    'Capsule cross section is a photo-based approximation, not a measured contour.',
    'User accepted fit_30 tightness. Additional insertion depth needs clarification; rim angle, axial taper and sealing remain unmeasured.',
    'Rear dimensions and flat washer are provisional; only insertion length 8 mm is measured.',
    'Rear taper is a fit mock-up, not a verified positive lock. Do not drill the toy from this draft.',
    'Section wall checks are sampled in XY, not a global normal wall-thickness proof.',
    'Independent mesh triangle self-intersection test NOT_RUN; OpenCascade BRep validity and mesh topology checked.',
    'Fit_30 was sent to the connected X2D and physically tried by the user; see design/print-job-2026-09-21.md and design/fit-feedback.md. Rear adapter printing, retention, suction and leak tests NOT_RUN.'
]
(OUT/'geometry-report.json').write_text(json.dumps(REPORT,indent=2,ensure_ascii=False))
print(json.dumps({'parts':list(REPORT['parts']),'minimum_sampled_wall_mm':REPORT['minimum_sampled_wall_mm'],'fit_set_3mf':REPORT['fit_set_3mf']},indent=2))
