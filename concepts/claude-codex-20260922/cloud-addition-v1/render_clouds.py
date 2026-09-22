"""Actual A-series CAD views; no generative images or textures."""
import json
from PIL import Image,ImageDraw,ImageFont
from cloud_models import ROOT
import render_models as renderer
renderer.ROOT=ROOT


def main():
    manifest=json.loads((ROOT/'output/manifest.json').read_text())
    out=ROOT/'output/previews';out.mkdir(exist_ok=True)
    font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',31)
    names={'A1':'CLOUD BERET','A2':'TOO MUCH CLOUD','A3':'CLOUD AFRO','A4':'SLEEPY CLOUD'}
    sheet=Image.new('RGB',(1700,1620),'#F6F3EB');draw=ImageDraw.Draw(sheet)
    for i,model in enumerate(manifest['models']):
        key=model['id'];parts=[p for p in manifest['parts'] if p['design']==key]
        f=out/f'{key}-iso.png';renderer.render(parts,f)
        x=i%2*850;y=i//2*810
        sheet.paste(Image.open(f),(x,y+50));draw.text((x+25,y+12),f'{key} / {names[key]} / {model["height_mm"]:g} mm',font=font,fill='#252830')
        views=Image.new('RGB',(1700,1580),'#F6F3EB');vd=ImageDraw.Draw(views)
        for j,v in enumerate(['front','side','back','iso']):
            vf=out/f'{key}-{v}-solid.png';renderer.render(parts,vf,v,True)
            vx=j%2*850;vy=j//2*790;views.paste(Image.open(vf),(vx,vy+35));vd.text((vx+25,vy+5),f'{key} / {v.upper()} / SOLID',font=font,fill='#252830')
        views.save(out/f'{key}-views.png')
    sheet.save(out/'A1-A4-models.png')
    print(out/'A1-A4-models.png')

if __name__=='__main__':main()
