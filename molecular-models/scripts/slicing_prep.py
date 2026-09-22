"""Create first-print geometry and fully resolved, offline Bambu Studio presets."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import trimesh

ROOT=Path(__file__).resolve().parents[1]


def resolve_preset(folder,name,stack=()):
    if name in stack:raise ValueError('Preset inheritance cycle')
    src=json.loads((Path(folder)/(name+'.json')).read_text())
    out={}
    if src.get('inherits'):out.update(resolve_preset(folder,src['inherits'],(*stack,name)))
    for include in src.get('include',[]):out.update(resolve_preset(folder,include,(*stack,name)))
    out.update({k:v for k,v in src.items() if k not in {'inherits','include'}})
    return out


def flatback(mesh):
    """Keep the upper half at original z>=0; no change to the source model."""
    box=trimesh.creation.box([400,400,400]);box.apply_translation([0,0,200])
    return trimesh.boolean.intersection([mesh,box],engine='manifold')


def validate_presets(machine,filament):
    if machine.get('printer_model')!='Bambu Lab X2D':raise ValueError('Wrong printer')
    start=machine.get('machine_start_gcode','')
    if len(start)<1000 or 'M' not in start:raise ValueError('Missing model-specific start template')
    if float(filament.get('filament_density',['0'])[0])<=0:raise ValueError('Missing filament density')
    if float(filament.get('textured_plate_temp',['0'])[0])<50:raise ValueError('Incomplete PLA thermal preset')


def prepare(preset_root):
    dest=ROOT/'slicing';(dest/'presets').mkdir(parents=True,exist_ok=True)
    src=ROOT/'output/caffeine.stl';m=flatback(trimesh.load_mesh(src))
    from build import clean
    m=clean(m);m.export(dest/'caffeine_flatback_trial.stl')
    machine_name='Bambu Lab X2D 0.4 nozzle'
    process_name='0.16mm Standard @BBL X2D'
    filament_name='Bambu PLA Basic @BBL X2D 0.4 nozzle'
    machine=resolve_preset(preset_root/'machine',machine_name)
    process=resolve_preset(preset_root/'process',process_name)
    filament=resolve_preset(preset_root/'filament',filament_name)
    validate_presets(machine,filament)
    machine.update(name='Molecular trial X2D 0.4',inherits=machine_name,**{'from':'User'})
    process.update(name='Molecular trial 0.16mm',inherits=process_name,**{'from':'User'},
        curr_bed_type='Textured PEI Plate',wall_loops='3',sparse_infill_density='20%',
        brim_type='outer_only',brim_width='5',brim_object_gap='0.1',enable_support='0',
        initial_layer_speed=['30']*6,outer_wall_speed=['60']*6,enable_prime_tower='0')
    filament.update(name='Molecular trial black PLA',inherits=filament_name,**{'from':'User'},
        filament_colour=['#000000'])
    for name,data in [('machine',machine),('process',process),('filament',filament)]:
        (dest/'presets'/f'{name}.json').write_text(json.dumps(data,indent=2)+'\n')
    p=trimesh.load_mesh(dest/'caffeine_flatback_trial.stl')
    report=dict(stage='First prototype; final physical checks required before printing',
        source_sha256=hashlib.sha256(src.read_bytes()).hexdigest(),
        caffeine_original_preserved=True,flatback_plane_original_z_mm=0,
        flatback_extents_mm=p.extents.tolist(),flatback_watertight=bool(p.is_watertight),
        flatback_bodies=int(p.body_count),nozzle_mm=.4,layer_mm=.16,
        filament='Bambu PLA Basic black, AMS slot 1 observed in connected-device UI',
        bed='Textured PEI Plate, saved slicer selection; operator verification is recorded separately',
        preset_names=dict(machine=machine_name,process=process_name,filament=filament_name),
        parameters=dict(walls=3,infill='20%',support=False,outer_brim_mm=5,brim_gap_mm=.1,
            first_layer_mm_s=30,outer_wall_mm_s=60),
        start_gcode_template_characters=len(machine['machine_start_gcode']),
        filament_density_g_cm3=filament['filament_density'],
        sources='Installed official BambuStudio system/BBL presets, recursively resolving inherits and include')
    (dest/'preparation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--preset-root',type=Path,required=True)
    prepare(p.parse_args().preset_root)
