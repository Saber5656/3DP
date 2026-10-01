"""Export actual revised meshes and fit coupons, preserving every v1 artifact."""
from pathlib import Path
import argparse,hashlib,json
import numpy as np
import trimesh
from refined_models import ROOT,COLORS,build_model,fit_coupon,portable_mesh,print_solid,Part
from export_models import write_3mf


def save_part(part,key,out):
    name=f'{key}_{part.name}'
    display=portable_mesh(part.solid);bed=portable_mesh(print_solid(part))
    target=out/'stl'/f'{name}.stl';assembly=out/'assembly'/f'{name}.stl'
    bed.export(target);display.export(assembly)
    reloaded=trimesh.load_mesh(target,process=True)
    assert reloaded.is_watertight and reloaded.is_volume and reloaded.body_count==1,name
    assert np.all(reloaded.area_faces>0) and abs(reloaded.bounds[0,2])<1e-5,name
    assert np.allclose(reloaded.extents,bed.extents,atol=1e-4),name
    return {'id':name,'design':key,'part':part.name,'color':part.color,'count':1,'stl':str(target.relative_to(ROOT)),'assembly_stl':str(assembly.relative_to(ROOT)),'orientation':part.orientation,'support_recommended':part.support,'print_extents_mm':bed.extents.tolist(),'assembly_bounds_mm':display.bounds.tolist(),'volume_mm3':float(bed.volume),'watertight':True,'components':1,'faces':len(bed.faces),'sha256':hashlib.sha256(target.read_bytes()).hexdigest()},display,bed


def export_all(height_mm=48):
    if height_mm!=48:
        raise ValueError('v2 automatic CAD export is validated at 48 mm only; rescale the delivered meshes together and recheck fit for other sizes.')
    out=ROOT/'output'
    for name in ['stl','assembly','fit-tests','optional-onepiece','print-plates','previews']:(out/name).mkdir(parents=True,exist_ok=True)
    records=[];models=[];fixtures=[]
    for key in ['A2','A3']:
        d=build_model(key,height_mm);assembled=[];scene=trimesh.Scene();printable=[]
        for part in d.parts:
            record,display,bed=save_part(part,key,out);records.append(record);assembled.append((record['id'],part.color,display));printable.append((record['id'],part.color,bed))
            glb=display.copy();glb.visual.face_colors=list(bytes.fromhex(COLORS[part.color][1:]))+[255]
            glb.apply_transform(trimesh.transformations.rotation_matrix(-np.pi/2,[1,0,0]));glb.apply_scale(.001);scene.add_geometry(glb,node_name=record['id'])
        write_3mf(assembled,out/'assembly'/f'{key}-v2-assembled.3mf');scene.export(out/'assembly'/f'{key}-v2-assembled.glb')
        q=trimesh.load(out/'assembly'/f'{key}-v2-assembled.3mf');assert abs(q.extents[2]-height_mm)<1e-4 and len(q.geometry)==7
        q=trimesh.load(out/'assembly'/f'{key}-v2-assembled.glb');assert abs(q.extents[1]-height_mm/1000)<1e-7
        # A slicer-neutral mesh plate, not printer G-code. Hidden seams face bed.
        white=[];x=10
        for name,color,bed in printable:
            if color!='white':continue
            item=bed.copy();item.apply_translation((x,10,0));white.append((name,color,item));x+=bed.extents[0]+8
        write_3mf(white,out/'print-plates'/f'{key}-v2-white-hidden-seams-down.3mf')
        mono=Part('cloud_onepiece','white',d.whole_cloud,'upright',True)
        monofile=out/'optional-onepiece'/f'{key}-v2-cloud-onepiece.stl';portable_mesh(print_solid(mono)).export(monofile)
        onepiece_assembly=assembled[:3]+[(f'{key}_cloud_onepiece','white',portable_mesh(d.whole_cloud))]
        onepiece_3mf=out/'optional-onepiece'/f'{key}-v2-onepiece-assembled.3mf'
        write_3mf(onepiece_assembly,onepiece_3mf)
        q=trimesh.load(onepiece_3mf);assert len(q.geometry)==4 and abs(q.extents[2]-height_mm)<1e-4
        bounds=np.vstack([display.bounds for _,_,display in assembled])
        models.append({'id':key,'height_mm':height_mm,'extents_mm':np.ptp(bounds,axis=0).tolist(),'parts':7,'quantity':1,'legacy_body_compatibility':'CAD checked; physical fit not tested','joint':d.joint,'optional_onepiece':str(monofile.relative_to(ROOT)),'optional_onepiece_assembly':str(onepiece_3mf.relative_to(ROOT))})
        if height_mm==48:
            for clearance in [.20,.25,.30]:
                for part in fit_coupon(key,clearance):
                    if part.name.endswith('key_test') and clearance!=.25:continue
                    path=out/'fit-tests'/f'{part.name}.stl';q=portable_mesh(print_solid(part));q.export(path)
                    assert q.is_volume and q.is_watertight and q.body_count==1
                    fixtures.append({'name':part.name,'design':key,'clearance_per_side_mm':None if part.name.endswith('key_test') else clearance,'stl':str(path.relative_to(ROOT)),'color':part.color,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    manifest={'unit':'mm','target_height_mm':height_mm,'selected_ids':['A2','A3'],'models':models,'parts':records,'fit_coupons':fixtures,'tripo_used':False,'modeling_method':'Parametric CAD and analytic cloud fields; existing locator dimensions retained; closed rear and bottom-only blind socket','physical_print_status':'NOT_RUN','device_sent':False,'assembly_method':'Glue front/back white shells using two alignment pins, then lower onto keyed head; eyes glue into retained pockets. Pins can be replaced by 1.75mm filament cut to 3.8mm.'}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'models':models,'parts':len(records),'fit_coupons':len(fixtures)},ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--height-mm',type=float,choices=[48.0],default=48);export_all(parser.parse_args().height_mm)
