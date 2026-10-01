"""Offline provisional slicing; no printer connection or physical slot binding."""
import json
import argparse
import os
from pathlib import Path
import subprocess
from build import ROOT, COLORS, build_model, write_3mf, orient_for_print, support_blockers_for_print


def resolve(folder, name):
    data = json.loads((folder / (name + '.json')).read_text())
    result = resolve(folder, data['inherits']) if data.get('inherits') else {}
    for inc in data.get('include', []):
        result.update(resolve(folder, inc))
    result.update({k: v for k, v in data.items() if k not in {'inherits', 'include'}})
    return result


def main(include_dots=False):
    out = ROOT / 'slicing' / ('with-dots' if include_dots else '')
    settings = out / 'presets'
    settings.mkdir(parents=True, exist_ok=True)
    installed = Path(os.environ.get('BAMBU_PRESET_ROOT', '/Applications/BambuStudio.app/Contents/Resources/profiles/BBL'))
    names = {'machine': 'Bambu Lab X2D 0.4 nozzle', 'process': '0.08mm High Quality @BBL X2D'}
    # Brand/physical colors are not confirmed; this is a geometry-only trial.
    filament_name = 'Generic PLA @BBL X2D 0.4 nozzle'
    machine = resolve(installed / 'machine', names['machine'])
    process = resolve(installed / 'process', names['process'])
    process.update(layer_height='0.08', wall_loops='4', sparse_infill_density='20%',
                   sparse_infill_pattern='gyroid', curr_bed_type='Textured PEI Plate',
                   enable_support='1', support_type='tree(auto)', support_on_build_plate_only='1',
                   bridge_no_support='1',
                   support_filament='1', support_interface_filament='1',
                   enable_prime_tower='1', brim_type='outer_only', brim_width='3',
                   print_sequence='by layer', filament_map_mode='Manual',
                   filament_map=['1'] * 4, wipe_tower_x=['10'], wipe_tower_y=['80'],
                   prime_tower_width='45')
    for name, data in [('machine', machine), ('process', process)]:
        data.update(name='524 keychain provisional ' + name, inherits=names[name], **{'from': 'User'})
        (settings / (name + '.json')).write_text(json.dumps(data, indent=2))
    filaments = []
    for color, value in COLORS.items():
        data = resolve(installed / 'filament', filament_name)
        data.update(name='524 provisional ' + color, inherits=filament_name, filament_colour=[value], **{'from': 'User'})
        path = settings / (color + '.json')
        path.write_text(json.dumps(data, indent=2))
        filaments.append(str(path))
    model = build_model(include_dots=include_dots)
    parts = {name: solid.translate([128, 110, 0])
             for name, solid in orient_for_print(model['parts']).items()}
    source = out / '524-face-up-color-source.3mf'
    blockers = {name: solid.translate([128, 110, 0]) for name, solid in support_blockers_for_print().items()}
    write_3mf(source, parts, COLORS, support_blockers=blockers)
    command = [os.environ.get('BAMBU_BIN', '/Applications/BambuStudio.app/Contents/MacOS/BambuStudio'),
               '--debug', '2', '--datadir', str(out / 'runtime'),
               '--load-settings', str(settings / 'machine.json') + ';' + str(settings / 'process.json'),
               '--load-filaments', ';'.join(filaments), '--curr-bed-type', 'Textured PEI Plate',
               '--orient', '0', '--arrange', '0', '--ensure-on-bed', '--slice', '0',
               '--export-3mf', str(out / '524-PROVISIONAL-DO-NOT-SEND.3mf'), str(source)]
    with (out / 'slice.log').open('w') as log:
        result = subprocess.run(command, cwd=out, stdout=log, stderr=subprocess.STDOUT, timeout=300)
    print('Bambu Studio exit:', result.returncode)
    if result.returncode:
        print((out / 'slice.log').read_text()[-8000:])
    result.check_returncode()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--with-dots', action='store_true')
    main(parser.parse_args().with_dots)
