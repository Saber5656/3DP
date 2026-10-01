"""Offline slice of the corrective design. This script never sends a print."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile
from xml.etree import ElementTree as ET

from build import (ROOT, V6, COLORS, build_model, coupon_for_print,
                   orient_for_print, support_blockers_for_print, write_3mf)

REFERENCE = V6/'print-run-20260927'/'524-Keychain-v6-Blue-Mouth-GUI-Verified.3mf'


def resolve(folder, name):
    data = json.loads((folder/(name+'.json')).read_text())
    result = resolve(folder,data['inherits']) if data.get('inherits') else {}
    for include in data.get('include',[]):
        result.update(resolve(folder,include))
    result.update({k:v for k,v in data.items() if k not in {'inherits','include'}})
    return result


def presets_for_cli(out, settings):
    """Supply real machine dimensions before the CLI validates a core 3MF."""
    installed = Path(os.environ.get('BAMBU_PRESET_ROOT',
                     '/Applications/BambuStudio.app/Contents/Resources/profiles/BBL'))
    dest = out/'presets'
    dest.mkdir(exist_ok=True)
    for kind, name in [('machine','Bambu Lab X2D 0.4 nozzle'),
                       ('process','0.08mm High Quality @BBL X2D')]:
        data = resolve(installed/kind,name)
        data.update({k:settings[k] for k in data if k in settings})
        if kind == 'process':
            data.update({k:settings[k] for k in [
                'enable_prime_tower','wipe_tower_no_sparse_layers','wipe_tower_x','wipe_tower_y',
                'support_top_z_distance','support_bottom_z_distance','support_interface_spacing',
                'support_interface_top_layers','filament_map','filament_map_mode']})
        data.update(name='524 v7 '+kind, inherits=name, **{'from':'User'})
        (dest/(kind+'.json')).write_text(json.dumps(data,indent=2))
    filaments = []
    names = ['Generic PLA','Bambu PLA Basic','Bambu PLA Basic','Bambu PLA Translucent']
    for i,(color,name) in enumerate(zip(COLORS.values(),names)):
        name += ' @BBL X2D 0.4 nozzle'
        data = resolve(installed/'filament',name)
        data.update(name=f'524 v7 filament {i+1}',inherits=name,filament_colour=[color],**{'from':'User'})
        path = dest/f'filament-{i+1}.json'
        path.write_text(json.dumps(data,indent=2))
        filaments.append(path)
    return dest, filaments


def configure_archive(source, settings, mapping):
    with zipfile.ZipFile(source) as z:
        files = {n:z.read(n) for n in z.namelist()}
    config = ET.fromstring(files['Metadata/model_settings.config'])
    for e in config.findall('plate/metadata'):
        if e.get('key') == 'filament_maps':
            e.set('value', ' '.join(mapping))
    files['Metadata/model_settings.config'] = ET.tostring(config)
    files['Metadata/project_settings.config'] = json.dumps(settings).encode()
    with zipfile.ZipFile(source, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, content in files.items():
            z.writestr(name, content)


def prepare(mode='full'):
    out = ROOT/'slicing'/mode
    out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(REFERENCE) as z:
        settings = json.loads(z.read('Metadata/project_settings.config'))
    settings.update(wipe_tower_no_sparse_layers='1', wipe_tower_x=['30'],
                    wipe_tower_y=['10'], support_top_z_distance='0.08',
                    support_bottom_z_distance='0.08', support_interface_spacing='0.20',
                    support_interface_top_layers='3', filament_map_mode='Manual',
                    filament_map=['1','2','1','1'])
    # Thin critical perimeters and overhangs need conservative speeds. Keep
    # the successful filament temperatures/fans and full purge matrix intact.
    for key, value in [('outer_wall_speed','40'), ('inner_wall_speed','40'), ('small_perimeter_speed','20'),
                       ('small_perimeter_threshold','10')]:
        settings[key] = [value]*len(settings.get(key, ['']))
    if mode == 'coupon':
        parts = {'yellow':coupon_for_print()}
        settings.update(enable_prime_tower='0', wipe_tower_no_sparse_layers='0')
        mapping = ['1']
    else:
        parts = orient_for_print(build_model()['parts'])
        mapping = ['1','2','1','1']
    parts = {n:s.translate([128,180,0]) for n,s in parts.items()}
    blockers = {n:s.translate([128,180,0]) for n,s in support_blockers_for_print().items()}
    source = out/'source.3mf'
    write_3mf(source, parts, COLORS, support_blockers=blockers)
    configure_archive(source, settings, mapping)
    presets, filaments = presets_for_cli(out, settings)
    return out, source, presets, filaments


def main(mode='full'):
    out, source, presets, filaments = prepare(mode)
    output = out/'524-v7-CANDIDATE-NOT-SENT.3mf'
    command = [os.environ.get('BAMBU_BIN','/Applications/BambuStudio.app/Contents/MacOS/BambuStudio'),
               '--debug','2','--datadir',str(out/'runtime'),
               '--load-settings',str(presets/'machine.json')+';'+str(presets/'process.json'),
               '--load-filaments',';'.join(map(str,filaments)), '--orient','0','--arrange','0',
               '--ensure-on-bed','--slice','0','--export-3mf',str(output),str(source)]
    with (out/'slice.log').open('w') as log:
        result = subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=300)
    print('slice exit:',result.returncode)
    print((out/'slice.log').read_text()[-2600:])
    result.check_returncode()
    repository = ROOT.parents[2]
    subprocess.run([sys.executable,str(repository/'tools/print_audit.py'),str(output.relative_to(repository)),
                    '--max-no-change-tower-g','0.1','--output',str(out/'audit.json')],
                   check=True,cwd=repository)
    subprocess.run([sys.executable,str(ROOT/'verify_paths.py'),str(output)],check=True)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=['full','coupon'],default='full')
    main(parser.parse_args().mode)
