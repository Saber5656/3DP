"""Slice the current verified manifest offline; never send to the printer."""
import json,hashlib
from pathlib import Path
from slicing_support import run_slice
ROOT=Path(__file__).resolve().parent

def main():
    manifest=json.loads((ROOT/'output/manifest.json').read_text())
    target=ROOT/'slice-work/final';target.mkdir(parents=True,exist_ok=True)
    results=[]
    for color in ('gray','translucent_blue','black','white','orange'):
        parts=[p for p in manifest['parts'] if p['color']==color]
        for p in parts:assert hashlib.sha256((ROOT/p['stl']).read_bytes()).hexdigest()==p['sha256']
        print('START',color,len(parts),flush=True)
        report=run_slice([ROOT/p['stl'] for p in parts],target/(color+'.3mf'),color,any(p['support_recommended'] for p in parts))
        results.append(report)
        (target/'reports-private.json').write_text(json.dumps(results,indent=2)+'\n')
        print('DONE',color,report['estimated_seconds'],report['estimated_filament_g'],flush=True)
    public=[{k:v for k,v in r.items() if k not in ('evidence_dir','cli_log','output_3mf')} for r in results]
    (target/'slice-reports.json').write_text(json.dumps(public,indent=2)+'\n')

if __name__=='__main__':main()
