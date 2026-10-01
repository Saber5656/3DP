"""Portable meshes and editable CAD; excludes printer G-code and private logs."""
from pathlib import Path
import hashlib,json,zipfile
ROOT=Path(__file__).resolve().parent
REPO=ROOT.parent


def main():
    files=[]
    for name in ['README.md','VALIDATION.md','REVIEW.md','requirements.txt','refined_models.py','export_refined.py','render_refined.py','validate_slices.py','make_bundle.py','tests/test_refinement.py']:
        files.append(ROOT/name)
    files+=sorted(p for p in (ROOT/'output').rglob('*') if p.is_file())
    for name in ['models.py','export_models.py','slicing_support.py','inspect_layers.py','requirements.txt']:
        files.append(REPO/'production-v1'/name)
    files.append(REPO/'cloud-addition-v1/cloud_models.py')
    # Faithful before/after renderer inputs, not additional print selections.
    for key in ['A2','A3']:
        for part in ['clawd','clawd_eye_1','clawd_eye_2','cloud']:
            files.append(REPO/'cloud-addition-v1/output/assembly'/f'{key}_{part}.stl')
    for name in ['artifact-roundtrip.json','offline-slices.json','white-halves-slice.json','orange-bodies-slice.json','white-fit-coupons-slice.json','white-halves-support-metadata-failure.json','white-halves-layers.png','orange-bodies-layers.png','white-fit-coupons-layers.png','regression-green.log','regression-red.log','export.log','independent-review.json']:
        files.append(ROOT/'evidence'/name)
    archive=ROOT/'ClaudeCloud-A2-A3-v2-48mm.zip'
    top='ClaudeCloud-A2-A3-v2-48mm'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        z.writestr(top+'/START-HERE.txt','A2/A3 revised models, 48 mm.\nRead cloud-refinement-v2/README.md.\nTripo was not used. Physical fit of v2 is not yet tested.\nModel files only; no print job will start automatically.\n')
        for path in sorted(set(files)):
            name=f'{top}/{path.relative_to(REPO)}'
            if path.suffix in {'.py','.md','.txt','.json','.log'}:
                value=path.read_text().replace(str(REPO),'${PROJECT_ROOT}').replace(str(Path.home()),'${HOME}')
                z.writestr(name,value)
            else:z.write(path,name)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert not any(name.endswith('.gcode') or '/slice-work/' in name for name in z.namelist())
    report={'file':archive.name,'size_bytes':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'files':len(set(files))+1,'includes':'A2/A3 v2 STL/3MF/GLB, coupons, actual mesh previews, parametric source plus dependencies','excludes':'Printer G-code, profiles, AMS settings, private logs, API credentials'}
    (ROOT/'evidence/bundle.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))

if __name__=='__main__':main()
