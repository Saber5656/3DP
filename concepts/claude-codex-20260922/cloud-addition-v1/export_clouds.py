"""Export A1–A4 only; existing D/B artifacts are never overwritten."""
import json,hashlib
import numpy as np
import trimesh
from cloud_models import ROOT,COLORS,build_clouds,mesh,print_solid,portable_mesh
from export_models import write_3mf


def export_all(height_mm=48):
    out=ROOT/'output';(out/'stl').mkdir(parents=True,exist_ok=True);(out/'assembly').mkdir(exist_ok=True)
    records=[];summaries=[]
    for key,d in build_clouds(height_mm).items():
        assembly=[];scene=trimesh.Scene()
        for p in d.parts:
            display=portable_mesh(p.solid);printable=portable_mesh(print_solid(p));name=key+'_'+p.name
            target=out/'stl'/f'{name}.stl';printable.export(target)
            loaded=trimesh.load_mesh(target,process=True)
            assert loaded.is_watertight and loaded.is_volume and loaded.body_count==1,name
            assert np.allclose(loaded.extents,printable.extents,atol=1e-4)
            assert abs(loaded.bounds[0,2])<1e-5
            assembly.append((name,p.color,display))
            glbmesh=display.copy();glbmesh.visual.face_colors=list(bytes.fromhex(COLORS[p.color][1:]))+[255]
            glbmesh.apply_transform(trimesh.transformations.rotation_matrix(-np.pi/2,[1,0,0]));glbmesh.apply_scale(.001)
            scene.add_geometry(glbmesh,node_name=name)
            assembly_file=out/'assembly'/f'{name}.stl';display.export(assembly_file)
            records.append({'id':name,'design':key,'part':p.name,'color':p.color,'count':1,
                'stl':str(target.relative_to(ROOT)),'assembly_stl':str(assembly_file.relative_to(ROOT)),
                'orientation':p.orientation,'support_recommended':p.support,
                'print_extents_mm':loaded.extents.tolist(),'assembly_bounds_mm':display.bounds.tolist(),
                'volume_mm3':float(loaded.volume),'watertight':bool(loaded.is_watertight),'components':loaded.body_count,
                'euler':loaded.euler_number,'faces':len(loaded.faces),'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
        write_3mf(assembly,out/'assembly'/f'{key}-assembled.3mf');scene.export(out/'assembly'/f'{key}-assembled.glb')
        assert np.isclose(trimesh.load(out/'assembly'/f'{key}-assembled.glb').extents[1],height_mm/1000,atol=1e-7)
        reread=trimesh.load(out/'assembly'/f'{key}-assembled.3mf')
        assert abs(reread.extents[2]-height_mm)<1e-4 and len(reread.geometry)==4
        b=np.vstack([m.bounds for _,_,m in assembly])
        summaries.append({'id':key,'height_mm':height_mm,'extents_mm':np.ptp(b,axis=0).tolist(),'parts':len(d.parts),'master_scale':d.scale,'quantity':1})
    manifest={'unit':'mm','target_height_mm':height_mm,'selected_ids':['A1','A2','A3','A4'],
        'corrected_print_selection':['A1','A2','A3','A4','B4','D3'],
        'models':summaries,'parts':records,'assembly_method':'Cloud lowers vertically onto keyed head with glue clearance; black eyes glue in. Physical fit not yet tested.',
        'physical_print_status':'NOT_RUN','device_sent':False}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'models':summaries,'parts':len(records)},ensure_ascii=False))

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--height-mm',type=float,default=48.)
    export_all(parser.parse_args().height_mm)
