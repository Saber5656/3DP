"""Render only exported triangle meshes; no image generation or texture tricks."""
from pathlib import Path
import json,os
import vtk
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parent
from models import COLORS


def render(parts,file,view='iso',mono=False):
    ren=vtk.vtkRenderer();ren.SetBackground(.965,.952,.924)
    for p in parts:
        reader=vtk.vtkSTLReader();reader.SetFileName(str(ROOT/p['assembly_stl']));reader.Update()
        normals=vtk.vtkPolyDataNormals();normals.SetInputConnection(reader.GetOutputPort());normals.SetFeatureAngle(55);normals.SplittingOn();normals.Update()
        mapper=vtk.vtkPolyDataMapper();mapper.SetInputConnection(normals.GetOutputPort())
        actor=vtk.vtkActor();actor.SetMapper(mapper)
        rgb=(.68,.70,.72) if mono else tuple(x/255 for x in bytes.fromhex(COLORS[p['color']][1:]))
        actor.GetProperty().SetColor(*rgb);actor.GetProperty().SetInterpolationToPhong();actor.GetProperty().SetAmbient(.18);actor.GetProperty().SetDiffuse(.82)
        ren.AddActor(actor)
    win=vtk.vtkRenderWindow();win.SetOffScreenRendering(1);win.SetSize(850,750);win.SetMultiSamples(8);win.AddRenderer(ren)
    bounds=ren.ComputeVisiblePropBounds();c=[(bounds[i*2]+bounds[i*2+1])/2 for i in range(3)]
    cam=ren.GetActiveCamera();cam.SetFocalPoint(*c)
    direction={'iso':(90,-180,85),'front':(0,-200,0),'back':(0,200,0),'side':(200,0,0),'top':(0,0,200)}[view]
    cam.SetPosition(*(c[i]+direction[i] for i in range(3)));cam.SetViewUp(0,1,0) if view=='top' else cam.SetViewUp(0,0,1)
    cam.ParallelProjectionOn();ren.ResetCamera();ren.ResetCameraClippingRange();win.Render()
    grab=vtk.vtkWindowToImageFilter();grab.SetInput(win);grab.SetInputBufferTypeToRGB();grab.ReadFrontBufferOff();grab.Update()
    writer=vtk.vtkPNGWriter();writer.SetFileName(str(file));writer.SetInputConnection(grab.GetOutputPort());writer.Write();win.Finalize()


def main():
    manifest=json.loads((ROOT/'output/manifest.json').read_text());out=ROOT/'output/previews';out.mkdir(exist_ok=True)
    font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',32)
    small=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',23)
    sheet=Image.new('RGB',(1700,2430),'#F6F3EB');draw=ImageDraw.Draw(sheet)
    for i,model in enumerate(manifest['models']):
        name=model['id'];parts=[p for p in manifest['parts'] if p['design']==name]
        f=out/f'{name}-iso.png';render(parts,f)
        x=(i%2)*850;y=(i//2)*810
        sheet.paste(Image.open(f),(x,y+50));draw.text((x+30,y+18),f'{name} / {model["height_mm"]:g} mm / actual model',font=font,fill='#252830')
        views=Image.new('RGB',(1700,1580),'#F6F3EB');vd=ImageDraw.Draw(views)
        for j,v in enumerate(['front','side','back','iso']):
            vf=out/f'{name}-{v}-solid.png';render(parts,vf,v,True)
            vx=j%2*850;vy=j//2*790;views.paste(Image.open(vf),(vx,vy+35));vd.text((vx+25,vy+8),f'{name} / {v.upper()} / SOLID',font=small,fill='#252830')
        views.save(out/f'{name}-views.png')
    draw.text((900,1700),f'D1-D4 + B4\nHeight: {manifest["target_height_mm"]:g} mm each\nColour-separated parts\nOpaque material geometry preview\nNot a photo of a physical print',font=font,fill='#252830',spacing=20)
    sheet.save(out/'all-models.png')
    print(out/'all-models.png')


if __name__=='__main__':main()
