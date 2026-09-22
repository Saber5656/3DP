"""Depth-buffered visual QA of the exported meshes, with a compact contact sheet."""
from pathlib import Path
import vtk
from PIL import Image, ImageDraw, ImageFont
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'output'
W,H=640,620
files=[('fit_30.stl','TESTED: fit 30'),('draft_rear_adapter.stl','DRAFT: rear adapter'),('inspection_cutaway.stl','SECTION: airflow passage')]
canvas=Image.new('RGB',(1920,850),'#fafaf8')
draw=ImageDraw.Draw(canvas)
font='/System/Library/Fonts/Supplemental/Arial.ttf'
f=ImageFont.truetype(font,28);small=ImageFont.truetype(font,22)
draw.text((45,24),'KIRBY VACUUM ADAPTER / FIT-FIRST CAD PROTOTYPE',font=f,fill='#22282d')
for idx,(filename,title) in enumerate(files):
 reader=vtk.vtkSTLReader();reader.SetFileName(str(OUT/filename));reader.Update()
 normals=vtk.vtkPolyDataNormals();normals.SetInputConnection(reader.GetOutputPort());normals.SetFeatureAngle(45);normals.SplittingOn();normals.ConsistencyOn();normals.Update()
 mapper=vtk.vtkPolyDataMapper();mapper.SetInputConnection(normals.GetOutputPort());mapper.ScalarVisibilityOff()
 actor=vtk.vtkActor();actor.SetMapper(mapper);actor.GetProperty().SetColor(.35,.47,.53);actor.GetProperty().SetInterpolationToPhong()
 ren=vtk.vtkRenderer();ren.SetBackground(250/255,250/255,248/255);ren.AddActor(actor)
 window=vtk.vtkRenderWindow();window.SetOffScreenRendering(1);window.SetSize(W,H);window.SetMultiSamples(4);window.AddRenderer(ren)
 bounds=actor.GetBounds();center=[(bounds[2*k]+bounds[2*k+1])/2 for k in range(3)]
 camera=ren.GetActiveCamera();camera.SetFocalPoint(*center);camera.SetPosition(center[0]+85,center[1]-130,center[2]+82);camera.SetViewUp(0,0,1);camera.ParallelProjectionOn()
 ren.ResetCamera();camera.SetParallelScale(37 if idx else 28);ren.ResetCameraClippingRange();window.Render()
 img=vtk.vtkWindowToImageFilter();img.SetInput(window);img.SetInputBufferTypeToRGB();img.ReadFrontBufferOff();img.Update()
 writer=vtk.vtkPNGWriter();writer.SetFileName(str(OUT/f'qa-view-{idx+1}.png'));writer.SetInputConnection(img.GetOutputPort());writer.Write();window.Finalize()
 canvas.paste(Image.open(OUT/f'qa-view-{idx+1}.png'),(idx*W,90))
 draw.text((idx*W+40,77),title,font=f,fill='#22282d')
 caption='36.4 x 12.4 mm stem; tightness accepted\n20 mm stem; depth clarification pending' if idx==0 else '20 mm bore; 8 mm rear stem\nRear fit and retention are unverified'
 draw.multiline_text((idx*W+40,710),caption,font=small,fill='#343c40',spacing=8)
draw.text((40,807),'Fit 30 selected. Do not enlarge the toy hole from the draft model.',font=small,fill='#6c4334')
canvas.save(OUT/'preview.png')
print('Depth-buffered STL preview saved.')
