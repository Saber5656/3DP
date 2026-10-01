"""Faithful before/after and socket views rendered from the actual meshes."""
import json
from pathlib import Path
import numpy as np
import trimesh,vtk
from PIL import Image,ImageDraw,ImageFont
from refined_models import ROOT,COLORS,build_model,mesh


def render(items,path,view='back_iso',size=(780,700),scale=None):
    renderer=vtk.vtkRenderer();renderer.SetBackground(.966,.955,.93)
    for name,color,m in items:
        points=vtk.vtkPoints()
        for xyz in m.vertices:points.InsertNextPoint(*xyz)
        cells=vtk.vtkCellArray()
        for a,b,c in m.faces:cells.InsertNextCell(3);cells.InsertCellPoint(int(a));cells.InsertCellPoint(int(b));cells.InsertCellPoint(int(c))
        poly=vtk.vtkPolyData();poly.SetPoints(points);poly.SetPolys(cells)
        normals=vtk.vtkPolyDataNormals();normals.SetInputData(poly);normals.SetFeatureAngle(55);normals.SplittingOn();normals.Update()
        mapper=vtk.vtkPolyDataMapper();mapper.SetInputConnection(normals.GetOutputPort())
        actor=vtk.vtkActor();actor.SetMapper(mapper);actor.GetProperty().SetColor(*[c/255 for c in bytes.fromhex(COLORS[color][1:])]);actor.GetProperty().SetInterpolationToPhong();actor.GetProperty().SetAmbient(.20);actor.GetProperty().SetDiffuse(.80);renderer.AddActor(actor)
    bounds=renderer.ComputeVisiblePropBounds();center=[(bounds[i*2]+bounds[i*2+1])/2 for i in range(3)]
    camera=renderer.GetActiveCamera();camera.SetFocalPoint(*center)
    directions={'front':(0,-200,0),'back':(0,200,0),'back_iso':(100,180,70),'front_iso':(100,-180,70),'socket':(25,-180,-95),'section':(0,-200,15)}
    direction=directions[view];camera.SetPosition(*[center[i]+direction[i] for i in range(3)]);camera.SetViewUp(0,0,1);camera.ParallelProjectionOn();renderer.ResetCamera()
    if scale:camera.SetParallelScale(scale)
    renderer.ResetCameraClippingRange()
    window=vtk.vtkRenderWindow();window.SetOffScreenRendering(1);window.SetSize(*size);window.SetMultiSamples(8);window.AddRenderer(renderer);window.Render()
    capture=vtk.vtkWindowToImageFilter();capture.SetInput(window);capture.SetInputBufferTypeToRGB();capture.ReadFrontBufferOff();capture.Update();writer=vtk.vtkPNGWriter();writer.SetFileName(str(path));writer.SetInputConnection(capture.GetOutputPort());writer.Write();window.Finalize()


def main():
    out=ROOT/'output/previews';out.mkdir(exist_ok=True)
    font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',26)
    small=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',20)
    sheet=Image.new('RGB',(2340,1510),'#F6F3ED');draw=ImageDraw.Draw(sheet)
    hero=Image.new('RGB',(1560,790),'#F6F3ED');hd=ImageDraw.Draw(hero)
    for row,key in enumerate(['A2','A3']):
        d=build_model(key);new=[(p.name,p.color,mesh(p.solid)) for p in d.parts]
        olddir=ROOT.parent/'cloud-addition-v1/output/assembly'
        prior=[(p.name,p.color,trimesh.load_mesh(olddir/f'{key}_{p.name}.stl')) for p in d.parts if p.name in ('clawd','clawd_eye_1','clawd_eye_2')]
        prior.append(('cloud','white',trimesh.load_mesh(olddir/f'{key}_cloud.stl')))
        for name,items,view in [('v1-back',prior,'back_iso'),('v2-back',new,'back_iso'),('v2-front',new,'front_iso')]:render(items,out/f'{key}-{name}.png',view)
        for col,filename,title in [(0,f'{key}-v1-back.png',f'{key} / V1 BACK'),(1,f'{key}-v2-back.png',f'{key} / V2 ROUNDED BACK')]:
            sheet.paste(Image.open(out/filename),(col*780,row*745+40));draw.text((col*780+20,row*745+10),title,font=font,fill='#242424')
        section=[]
        for name,color,m in new:
            if name=='cloud_front' or name.startswith('cloud_pin'):continue
            q=m.copy()
            if color!='white':q.apply_translation((0,0,-7))
            section.append((name,color,q))
        render(section,out/f'{key}-socket-cutaway.png','section')
        sheet.paste(Image.open(out/f'{key}-socket-cutaway.png'),(1560,row*745+40));draw.text((1580,row*745+10),f'{key} / SOCKET + KEY (FRONT REMOVED)',font=font,fill='#242424')
        render([('cloud','white',mesh(d.whole_cloud))],out/f'{key}-socket-underside.png','socket')
        hero.paste(Image.open(out/f'{key}-v2-front.png'),(780*row,40));hd.text((780*row+20,10),f'{key} / V2 / ASSEMBLED HEIGHT 48 mm',font=font,fill='#242424')
    draw.text((20,1490),'Actual CAD mesh views. Physical print and fit test pending.',font=small,fill='#454545')
    sheet.save(out/'A2-A3-v1-v2-comparison.png');hero.save(out/'A2-A3-v2-models.png');print(out/'A2-A3-v1-v2-comparison.png')

if __name__=='__main__':main()
