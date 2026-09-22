"""Export real parts, assembly colour previews and portable 3MFs."""
import json,hashlib,zipfile,xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
import trimesh
from models import ROOT,COLORS,build_all,mesh,print_solid


def write_3mf(parts,path):
    ns='http://schemas.microsoft.com/3dmanufacturing/core/2015/02'
    ET.register_namespace('',ns)
    tag=lambda x:f'{{{ns}}}{x}'
    root=ET.Element(tag('model'),{'unit':'millimeter','{http://www.w3.org/XML/1998/namespace}lang':'en-US'})
    resources=ET.SubElement(root,tag('resources'));build=ET.SubElement(root,tag('build'))
    mats=ET.SubElement(resources,tag('basematerials'),{'id':'1'})
    palette=list(COLORS)
    for color in palette:ET.SubElement(mats,tag('base'),{'name':color,'displaycolor':COLORS[color]+'FF'})
    for i,(name,color,m) in enumerate(parts,2):
        obj=ET.SubElement(resources,tag('object'),{'id':str(i),'type':'model','name':name,'pid':'1','pindex':str(palette.index(color))})
        me=ET.SubElement(obj,tag('mesh'));ve=ET.SubElement(me,tag('vertices'));tr=ET.SubElement(me,tag('triangles'))
        for v in m.vertices:ET.SubElement(ve,tag('vertex'),dict(zip(('x','y','z'),(f'{x:.6f}' for x in v))))
        for f in m.faces:ET.SubElement(tr,tag('triangle'),dict(zip(('v1','v2','v3'),map(str,f))))
        ET.SubElement(build,tag('item'),{'objectid':str(i)})
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('3D/3dmodel.model',ET.tostring(root,encoding='utf-8',xml_declaration=True))
        z.writestr('[Content_Types].xml','<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
        z.writestr('_rels/.rels','<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')


def export_all(height_mm=48.0):
    out=ROOT/'output';(out/'stl').mkdir(parents=True,exist_ok=True)
    (out/'assembly').mkdir(exist_ok=True)
    records=[];summaries=[]
    for key,d in build_all(height_mm).items():
        assembly=[];scene=trimesh.Scene()
        for p in d.parts:
            display=mesh(p.solid);printable=mesh(print_solid(p));name=key+'_'+p.name
            target=out/'stl'/f'{name}.stl';printable.export(target)
            loaded=trimesh.load_mesh(target,process=True)
            assert loaded.is_watertight and loaded.is_volume and loaded.body_count==1,name
            assert np.allclose(loaded.extents,printable.extents,atol=1e-4)
            assert abs(loaded.bounds[0,2])<1e-5
            assembly.append((name,p.color,display))
            glbmesh=display.copy();rgb=list(bytes.fromhex(COLORS[p.color][1:]))+[255]
            glbmesh.apply_transform(trimesh.transformations.rotation_matrix(-np.pi/2,[1,0,0]))
            glbmesh.apply_scale(.001)  # glTF is metres and Y-up.
            glbmesh.visual.face_colors=rgb;scene.add_geometry(glbmesh,node_name=name)
            # Assemble view STL is intentionally not bed-oriented.
            assembled_file=out/'assembly'/f'{name}.stl';display.export(assembled_file)
            records.append({'id':name,'design':key,'part':p.name,'color':p.color,'count':1,
                'stl':str(target.relative_to(ROOT)),'assembly_stl':str(assembled_file.relative_to(ROOT)),
                'orientation':p.orientation,'support_recommended':p.support,
                'print_extents_mm':loaded.extents.tolist(),'assembly_bounds_mm':display.bounds.tolist(),
                'volume_mm3':float(loaded.volume),'watertight':bool(loaded.is_watertight),
                'components':loaded.body_count,'euler':loaded.euler_number,'faces':len(loaded.faces),
                'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
        write_3mf(assembly,out/'assembly'/f'{key}-assembled.3mf')
        scene.export(out/'assembly'/f'{key}-assembled.glb')
        glb_roundtrip=trimesh.load(out/'assembly'/f'{key}-assembled.glb')
        assert np.isclose(glb_roundtrip.extents[1],height_mm/1000,atol=1e-7)
        bounds=np.vstack([m.bounds for _,_,m in assembly]);ext=np.ptp(bounds,axis=0)
        summaries.append({'id':key,'height_mm':d.height_mm,'extents_mm':ext.tolist(),'parts':len(d.parts),
                          'master_scale':d.scale,'quantity':1})
    manifest={'unit':'mm','target_height_mm':height_mm,'selected_ids':['D1','D2','D3','D4','B4'],
        'quantity_note':'D3 repeated in request; one copy included unless requested otherwise.',
        'models':summaries,'parts':records,'assembly_method':'Color-separated parts, matching shallow recesses, glue assembly. Physical fit not yet tested.',
        'physical_print_status':'NOT_RUN','device_sent':False}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'models':summaries,'parts':len(records),'output':str(out)},ensure_ascii=False))


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--height-mm',type=float,default=48.0)
    args=parser.parse_args()
    if not 40<=args.height_mm<=150:parser.error('Supported height range: 40–150 mm; reslice after resizing.')
    export_all(args.height_mm)
