from pathlib import Path
import vtk
from PIL import Image,ImageDraw,ImageFont
P=Path(__file__).resolve().parent/'output/body-v3'
canvas=Image.new('RGB',(1440,850),'#f8f8f5')
draw=ImageDraw.Draw(canvas)
font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',28)
small=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',22)
draw.text((35,20),'KIRBY / REAR ADAPTER V3 / BLACK PLA',font=font,fill='#242b31')
for i,(name,title,scale) in enumerate([('kirby_body_v3_5mm_OD','BODY - 53 mm',35)]):
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
draw.text((760,170),'REAR INSERT',font=font,fill='#242b31')
draw.text((760,215),'OUTSIDE diameter: 5 mm',font=font,fill='#242b31')
draw.text((760,260),'Air passage: 3 mm',font=font,fill='#242b31')
draw.text((760,305),'Insertion length: 8 mm',font=font,fill='#242b31')
draw.text((760,365),'14 mm shoulder stays OUTSIDE the toy.',font=small,fill='#38434b')
# Dimension diagram, deliberately separate from actual STL rendering.
x,y=1000,550
for radius,fill in [(100,'#353f47'),(60,'#f8f8f5')]:draw.ellipse((x-radius,y-radius,x+radius,y+radius),fill=fill)
draw.line((900,675,1100,675),fill='#242b31',width=3)
draw.text((965,686),'5 mm',font=small,fill='#242b31')
caption=['Tested vacuum fit: 36.4 x 12.4 mm; stem 20 mm','Rear insert: 5 mm OUTSIDE / 3 mm INSIDE / 8 mm length','Use existing 5 mm rear hole. Do not enlarge it. Physical fit and suction need trial.']
for k,line in enumerate(caption):draw.text((35,752+k*29),line,font=small,fill='#38434b')
canvas.save(P/'preview.png')
