from pathlib import Path
import vtk
from PIL import Image,ImageDraw,ImageFont
P=Path(__file__).resolve().parent/'output/body-v2'
canvas=Image.new('RGB',(1440,850),'#f8f8f5')
draw=ImageDraw.Draw(canvas)
font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',28)
small=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',22)
draw.text((35,20),'KIRBY / REAR ADAPTER V2 / BLACK PLA',font=font,fill='#242b31')
for i,(name,title,scale) in enumerate([('kirby_body_v2','BODY - 75 mm',48),('retaining_nut_v2','RETAINING RING - 36 x 8 mm',24)]):
 reader=vtk.vtkSTLReader();reader.SetFileName(str(P/f'{name}.stl'));reader.Update()
 normals=vtk.vtkPolyDataNormals();normals.SetInputConnection(reader.GetOutputPort());normals.SetFeatureAngle(42);normals.SplittingOn();normals.Update()
 mapper=vtk.vtkPolyDataMapper();mapper.SetInputConnection(normals.GetOutputPort())
 actor=vtk.vtkActor();actor.SetMapper(mapper);actor.GetProperty().SetColor(.22,.26,.29)
 ren=vtk.vtkRenderer();ren.SetBackground(248/255,248/255,245/255);ren.AddActor(actor)
 win=vtk.vtkRenderWindow();win.SetOffScreenRendering(1);win.SetSize(720,650);win.AddRenderer(ren)
 b=actor.GetBounds();center=[(b[2*k]+b[2*k+1])/2 for k in range(3)]
 cam=ren.GetActiveCamera();cam.SetFocalPoint(*center);cam.SetPosition(center[0]+100,center[1]-140,center[2]+105);cam.SetViewUp(0,0,1);cam.ParallelProjectionOn();ren.ResetCamera();cam.SetParallelScale(scale);ren.ResetCameraClippingRange();win.Render()
 im=vtk.vtkWindowToImageFilter();im.SetInput(win);im.SetInputBufferTypeToRGB();im.ReadFrontBufferOff();im.Update()
 writer=vtk.vtkPNGWriter();writer.SetFileName(str(P/f'{name}.png'));writer.SetInputConnection(im.GetOutputPort());writer.Write();win.Finalize()
 canvas.paste(Image.open(P/f'{name}.png'),(i*720,105))
 draw.text((i*720+35,77),title,font=font,fill='#242b31')
caption=['Tested vacuum fit: 36.4 x 12.4 mm; stem 20 mm','Custom thread: 28 mm diameter / 4 mm pitch','Install ring through the opened mouth; check fit before cutting the back.']
for k,line in enumerate(caption):draw.text((35,752+k*29),line,font=small,fill='#38434b')
canvas.save(P/'preview.png')
