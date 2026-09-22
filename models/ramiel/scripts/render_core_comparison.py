"""Compare the v5 and current core using their actual CAD, with identical views."""
import json, subprocess, sys, types
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build import ROOT, build_models, box
from render import plt, draw
previous = '30c0db103bfe33fc99f293e7f241e15da9aaeb0f'
source = subprocess.check_output(['git', 'show', previous + ':build.py'], cwd=ROOT, text=True)
old = types.ModuleType('ramiel_v5'); old.__file__ = str(ROOT / 'build.py')
exec(compile(source, 'ramiel_v5.py', 'exec'), old.__dict__)
old_cfg = json.loads(subprocess.check_output(['git', 'show', previous + ':design.json'], cwd=ROOT))
cfg = json.loads((ROOT / 'design.json').read_text())
models = [('BEFORE / V5', old.build_models(old_cfg)), ('AFTER / V6', build_models(cfg))]
fig = plt.figure(figsize=(14, 10), facecolor='#0b1220')
for row, (view, elev, azim) in enumerate([('FRONT', 87, -90), ('OBLIQUE', 55, -55)]):
    for col, (label, model) in enumerate(models):
        body = model['parts']['star_body']
        bead = model['parts']['red_core'].translate([0, 0, cfg['star_bead_center_z']])
        pieces = [('star_body', body ^ box([84, 84, 70], [-42, -42, -20])), ('red_core', bead)]
        ax = fig.add_subplot(2, 2, row * 2 + col + 1)
        draw(ax, pieces, elev, azim)
        ax.set_title(label + ' / ' + view, color='white', fontsize=13)
fig.suptitle('RAMIEL / CORE RECESS CORRECTION', color='white', fontsize=21)
fig.text(.04, .025, 'Actual geometry, same cameras and crop. The ten sloping faces and five V valleys are part of the blue shell; no red paint is simulated.', color='#9cb5d7', fontsize=10)
fig.subplots_adjust(top=.9, bottom=.07, wspace=-.05, hspace=.04)
fig.savefig(ROOT / 'printing/star-v6/core-comparison.png', dpi=140)
plt.close(fig)
