"""Offline validation only; never opens a printer connection or sends a job."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'production-v1'))
from slicing_support import run_slice
from inspect_layers import inspect


def main():
    work=ROOT/'slice-work';work.mkdir(exist_ok=True)
    evidence=ROOT/'evidence';reports=[]
    stl=ROOT/'output/stl';coupons=ROOT/'output/fit-tests'
    jobs=[
        ('white-halves','white',False,[stl/f'{k}_{p}.stl' for k in ['A2','A3'] for p in ['cloud_front','cloud_back','cloud_pin_1','cloud_pin_2']]),
        ('orange-bodies','orange',True,[stl/f'{k}_clawd.stl' for k in ['A2','A3']]),
        ('white-fit-coupons','white',False,sorted(coupons.glob('*socket*.stl'))),
    ]
    for name,color,support,paths in jobs:
        out=work/f'{name}.3mf'
        if out.exists():raise FileExistsError(out)
        report=run_slice(paths,out,color,support)
        layers=inspect(out)
        # Public evidence carries no machine-local path or active AMS assignment.
        compact={k:v for k,v in report.items() if k not in ['evidence_dir','cli_log','output_3mf','layers']}
        compact.update(name=name,input_files=[str(p.relative_to(ROOT)) for p in paths],layer_validation=layers)
        (evidence/f'{name}-slice.json').write_text(json.dumps(compact,ensure_ascii=False,indent=2)+'\n')
        preview=work/layers['preview'];(evidence/preview.name).write_bytes(preview.read_bytes())
        reports.append(compact)
        print(json.dumps({'job':name,'seconds':report['estimated_seconds'],'grams':report['estimated_filament_g'],'support':report['support_used'],'objects':len(layers['objects'])}),flush=True)
    (evidence/'offline-slices.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':main()
