"""Generate design-stage STL, colour 3MF/GLB and scientific preview sheets."""
from __future__ import annotations

import json
import math
import sys
import zipfile
from collections import defaultdict
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring

import numpy as np
import trimesh
import manifold3d
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Line3DCollection, Poly3DCollection

from design import *

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"output";OUT.mkdir(exist_ok=True)
COLORS={"C":"#32383f","N":"#367ed2","O":"#ee852c","Zn":"#939da9","H":"#f1f0e8"}
# Selected by the user after the black-PLA coupon trial on 2026-09-21.
MOF_SOCKET_DIAMETER_MM=3.5
REPORT={"stage":"Design prototype; coupon-selected MOF sockets; full MOF assembly not yet printed","models":{}}


def sphere(center,radius,subdiv=2):
    m=trimesh.creation.icosphere(subdivisions=subdiv,radius=radius)
    m.apply_translation(center);return m


def cylinder(a,b,radius,sections=24):
    a=np.asarray(a);b=np.asarray(b)
    return trimesh.creation.cylinder(radius=radius,segment=[a,b],sections=sections)


def union(meshes):
    if len(meshes)==1:return meshes[0].copy()
    return clean(trimesh.boolean.union(meshes,engine="manifold"))


def clean(mesh):
    # Boolean meshes may contain near-coincident vertices which collapse in STL
    # float32 round trips. Simplify at 0.0001 mm, far below print resolution.
    manifold=manifold3d.Manifold(manifold3d.Mesh(np.float32(mesh.vertices),np.uint32(mesh.faces)))
    if manifold.status()!=manifold3d.Error.NoError:raise RuntimeError(manifold.status())
    refined=manifold.set_tolerance(.0001).simplify(.0001).to_mesh()
    return trimesh.Trimesh(refined.vert_properties[:,:3],refined.tri_verts,process=False)


def molecular_mesh(model,p,atom_radius=3.5,bond_radius=1.7):
    parts=defaultdict(list)
    full=[]
    for e,v in zip(model["elements"],p):
        radius=(2.7 if e=="Zn" else 2.2) if model["name"].startswith("mof") else atom_radius
        atom=sphere(v,radius)
        parts[e].append(atom);full.append(atom)
    for i,j in model["bonds"]:
        whole_bond=cylinder(p[i],p[j],bond_radius)
        full.append(whole_bond)
        if model["elements"][i]==model["elements"][j]:
            parts[model["elements"][i]].append(whole_bond)
            continue
        mid=(p[i]+p[j])/2
        parts[model["elements"][i]].append(cylinder(p[i],mid,bond_radius))
        parts[model["elements"][j]].append(cylinder(mid,p[j],bond_radius))
    # Solidly merge same-colour spheres and half bonds; different materials meet at a plane.
    colored={e:union(meshes) for e,meshes in parts.items()}
    return union(full),colored


def save_3mf(path,parts):
    ns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
    root=Element("model",unit="millimeter",xmlns=ns)
    metadata=SubElement(root,"metadata",name="Title");metadata.text="Molecular models: design prototype"
    metadata=SubElement(root,"metadata",name="Description");metadata.text="Geometry and color only; no printer, nozzle, material profile or toolpath."
    resources=SubElement(root,"resources")
    materials=SubElement(resources,"basematerials",id="1")
    for key in COLORS:SubElement(materials,"base",name=key,displaycolor=COLORS[key].upper()+"FF")
    build=SubElement(root,"build")
    for index,(name,mesh,color_key) in enumerate(parts,start=2):
        obj=SubElement(resources,"object",id=str(index),type="model",name=name,pid="1",pindex=str(list(COLORS).index(color_key)))
        xm=SubElement(obj,"mesh");verts=SubElement(xm,"vertices");tris=SubElement(xm,"triangles")
        for xyz in mesh.vertices:SubElement(verts,"vertex",**dict(zip("xyz",[f"{v:.6f}" for v in xyz])))
        for tri in mesh.faces:SubElement(tris,"triangle",**dict(zip(["v1","v2","v3"],map(str,tri))))
        SubElement(build,"item",objectid=str(index))
    content='<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>'
    rels='<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>'
    with zipfile.ZipFile(path,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",content);z.writestr("_rels/.rels",rels)
        z.writestr("3D/3dmodel.model",tostring(root,encoding="utf-8",xml_declaration=True))


def save_glb(path,parts):
    scene=trimesh.Scene()
    for name,mesh,key in parts:
        m=mesh.copy();m.visual.vertex_colors=trimesh.visual.color.hex_to_rgba(COLORS[key])
        # glTF is metres and Y-up; print/CAD data stays millimetres and Z-up.
        m.apply_transform(np.array([[.001,0,0,0],[0,0,.001,0],[0,-.001,0,0],[0,0,0,1]]))
        scene.add_geometry(m,node_name=name,geom_name=name)
    path.write_bytes(scene.export(file_type="glb"))


def qa(mesh):
    return dict(watertight=bool(mesh.is_watertight),winding_consistent=bool(mesh.is_winding_consistent),
                volume_positive=bool(mesh.volume>0),connected_bodies=int(mesh.body_count),
                extent_mm=np.round(mesh.extents,3).tolist(),triangles=len(mesh.faces),
                volume_mm3=float(mesh.volume),degenerate_faces=int(np.count_nonzero(mesh.area_faces<1e-10)))


def export_stl(name,mesh):
    original=mesh
    mesh=clean(mesh)
    path=OUT/(name+".stl");mesh.export(path)
    read=trimesh.load_mesh(path)
    check=qa(read)
    check["roundtrip_max_bound_error_mm"]=float(np.abs(mesh.bounds-read.bounds).max())
    check["cleanup_max_bound_change_mm"]=float(np.abs(original.bounds-mesh.bounds).max())
    check["cleanup_volume_relative_change"]=float(abs(original.volume-mesh.volume)/original.volume)
    if not (check["watertight"] and check["winding_consistent"] and check["volume_positive"]):
        raise RuntimeError((name,check))
    return check


def setup_ax(ax,extent=150,elev=22,azim=-55,zoom=1):
    ax.set_facecolor("#f6f4ef");ax.view_init(elev=elev,azim=azim);ax.set_proj_type("ortho")
    ax.set_box_aspect([1,1,1],zoom=zoom);half=extent/2
    ax.set(xlim=(-half,half),ylim=(-half,half),zlim=(-half,half))
    ax.set_axis_off()


def draw_model(ax,model,p,atom_radius=3.5,bond_radius=1.7,override=None,alpha=1):
    # Queue all surfaces for a single depth-sorted collection per scene.
    # Separate collections incorrectly hide the guest's front-facing H lobes.
    if not hasattr(ax,'molecular_parts'):ax.molecular_parts=[]
    e=model["elements"]
    for key in sorted(set(e)):
        pts=p[np.array(e)==key]
        r=(2.7 if key=="Zn" else 2.2) if model["name"].startswith("mof") else atom_radius
        meshes=[sphere(x,r,1) for x in pts]
        color=override or COLORS[key]
        for i,j in model["bonds"]:
            mid=(p[i]+p[j])/2
            if e[i]==key:meshes.append(cylinder(p[i],mid,bond_radius,8))
            if e[j]==key:meshes.append(cylinder(mid,p[j],bond_radius,8))
        ax.molecular_parts.extend((mesh,color) for mesh in meshes)


def draw_guest(ax,g):
    if not hasattr(ax,'molecular_parts'):ax.molecular_parts=[]
    c=np.array(g["center_mm"])
    ax.molecular_parts.append((sphere(c,g["carbon_radius_mm"],2),COLORS['C']))
    for d in np.array(methane()["positions"])[1:]:
        p=c+d/np.linalg.norm(d)*g["hydrogen_offset_mm"]
        ax.molecular_parts.append((sphere(p,g["hydrogen_radius_mm"],2),COLORS['H']))


def finish_scene(ax):
    triangles=np.concatenate([mesh.triangles for mesh,color in ax.molecular_parts])
    colors=np.concatenate([np.tile(matplotlib.colors.to_rgba(color),(len(mesh.faces),1)) for mesh,color in ax.molecular_parts])
    ax.add_collection3d(Poly3DCollection(triangles,facecolors=colors,shade=True,
        lightsource=matplotlib.colors.LightSource(azdeg=300,altdeg=50)))


def build():
    data=[]
    h=load_sdf(ROOT/"sources/helicene.sdf")
    p,scale=scaled_positions(h,100,3.5)
    for label,model,pts in [("helicene_A",h,p),("helicene_B",mirror(h),p*np.array([-1,1,1]))]:
        print('building',label,flush=True)
        mesh,color=molecular_mesh(model,pts)
        check=export_stl(label,mesh)
        parts=[(e,m,e) for e,m in color.items()]
        if label.endswith("B"):parts=[(name,m,"Zn") for name,m,k in parts]
        save_3mf(OUT/(label+".3mf"),parts);save_glb(OUT/(label+".glb"),parts)
        REPORT["models"][label]=dict(qa=check,scale_mm_per_angstrom=scale,atoms=len(pts),bonds=len(model["bonds"]),coordinates=model["coordinates"],absolute_helicity="A/B mirror pair; P/M not assigned")
        data.append((label,model,pts))
    for label,model,width in [("infinitene",load_infinitene(ROOT/"sources"),140),("caffeine",load_sdf(ROOT/"sources/caffeine.sdf"),110)]:
        print('building',label,flush=True)
        pts,scale=scaled_positions(model,width,3.5)
        mesh,color=molecular_mesh(model,pts)
        check=export_stl(label,mesh);parts=[(e,m,e) for e,m in color.items()]
        save_3mf(OUT/(label+".3mf"),parts);save_glb(OUT/(label+".glb"),parts)
        REPORT["models"][label]=dict(qa=check,scale_mm_per_angstrom=scale,atoms=len(pts),bonds=len(model["bonds"]),coordinates=model["coordinates"])
        data.append((label,model,pts))
    print('building MOF',flush=True)
    m=build_mof(ROOT/"sources/IRMOF-1.cif")
    pts,scale=scaled_positions(m,150,2.7);g=analyze_guest(m,pts,scale)
    if g["central_clearance_mm"]<=1 or g["retention_margin_mm"]<=1:raise RuntimeError('Guest geometry does not fit')
    frame,colors=molecular_mesh(m,pts,bond_radius=1.65)
    centers=(np.array(m["cluster_centers"])-np.array(m["positions"]).mean(0))*scale
    z_values=sorted(set(np.round(centers[:,2],6)))
    # Cut through the axial single C-C bonds above the lower benzene rings.
    pore_mid=(z_values[0]+z_values[1])/2
    axial=[]
    for i,j in m["bonds"]:
        if m["elements"][i]==m["elements"][j]=="C" and np.linalg.norm(pts[i,:2]-pts[j,:2])<1e-6:
            if min(pts[i,2],pts[j,2])>pore_mid and max(pts[i,2],pts[j,2])<z_values[1]:
                axial.append((pts[i,2]+pts[j,2])/2)
    if len(axial)!=9:raise ValueError("Expected nine axial C-C assembly cut sites")
    split_z=float(np.mean(axial))
    joint_xy=sorted(set((round(x,6),round(y,6)) for x,y,z in centers))
    collars=[cylinder([x,y,split_z-4],[x,y,split_z+4],3.6,32) for x,y in joint_xy]
    full_frame=union([frame,*collars])
    box=trimesh.creation.box([400,400,400]);box.apply_translation([0,0,split_z-200])
    lower=trimesh.boolean.intersection([full_frame,box],engine="manifold")
    upper=trimesh.boolean.difference([full_frame,box],engine="manifold")
    holes=[cylinder([x,y,split_z-4.5],[x,y,split_z+.01],MOF_SOCKET_DIAMETER_MM/2,32) for x,y in joint_xy]
    pegs=[cylinder([x,y,split_z-4],[x,y,split_z+.3],1.5,32) for x,y in joint_xy]
    lower=trimesh.boolean.difference([lower,union(holes)],engine="manifold")
    upper=union([upper,*pegs])
    c=np.array(g["center_mm"])
    gs=[sphere(c,g["carbon_radius_mm"],3)]
    hs=[sphere(c+d/np.linalg.norm(d)*g["hydrogen_offset_mm"],g["hydrogen_radius_mm"],3) for d in np.array(methane()["positions"])[1:]]
    # Disjoint colour solids: H lobes clipped by central C; union gives one free guest.
    guest=union([*gs,*hs]);hydrogen=trimesh.boolean.difference([union(hs),gs[0]],engine="manifold")
    checks={"frame_lower":export_stl("mof5_lower",lower),"frame_upper":export_stl("mof5_upper",upper),"guest":export_stl("mof5_guest_CH4",guest)}
    # Grey collar denotes a mechanical assembly feature, not another chemical bond.
    previewparts=[(e,mesh,e) for e,mesh in colors.items()]+[("joint_collars",union(collars),"Zn"),("guest_C",gs[0],"C"),("guest_H",hydrogen,"H")]
    save_glb(OUT/"mof5_assembled.glb",previewparts)
    save_3mf(OUT/"mof5_guest_CH4.3mf",[("guest_C",gs[0],"C"),("guest_H",hydrogen,"H")])
    save_3mf(OUT/"mof5_assembly.3mf",[("lower",lower,"Zn"),("upper",upper,"Zn"),("guest",guest,"H")])
    # The assembly 3MF intentionally uses monochrome frame pieces; atomic-colour view is separate.
    coupon=trimesh.creation.box([38,16,7]);coupon.apply_translation([0,0,3.5])
    drills=[cylinder([x,0,2],[x,0,8],d/2,32) for x,d in zip([-11,0,11],[3.3,3.4,3.5])]
    coupon=trimesh.boolean.difference([coupon,union(drills)],engine="manifold")
    pin=cylinder([0,0,0],[0,0,9],1.5,32)
    checks["fit_coupon"]=export_stl("fit_coupon_3p3_3p4_3p5",coupon)
    checks["fit_pin"]=export_stl("fit_pin_3p0",pin)
    REPORT["models"]["mof5"]=dict(parts=checks,atoms=len(pts),bonds=len(m["bonds"]),clusters=m["cluster_count"],linkers=m["linker_count"],scale_mm_per_angstrom=scale,
        guest=g,split_z_mm=float(split_z),joints=9,peg_diameter_mm=3.0,socket_diameter_mm=MOF_SOCKET_DIAMETER_MM,engagement_mm=4.0,
        coordinates=m["coordinates"],finite_surface="Outward BDC linkers omitted; boundary Zn sites truncated; not an isolated stable molecule",
        color_status="Atomic colors in GLB and sheet; assembly 3MF frame is uniform grey for robust first prototype",
        clearance_scope="Ideal rigid geometry, no FDM tolerance/elasticity assessment; guest enlarged, stylized space filling")
    data.append(("mof5",m,pts))
    (OUT/"design-data.json").write_text(json.dumps({name:dict(model=model,positions_mm=p.tolist()) for name,model,p in data},indent=2))
    (OUT/"validation.json").write_text(json.dumps(REPORT,indent=2))
    render_design(data,m,pts,g,lower,upper,gs,hydrogen)


def render_design(data,m,pts,g,lower,upper,gs,hydrogen):
    print('rendering sheets',flush=True)
    # Draw unclipped H surfaces to avoid coplanar colour-interface artefacts.
    # The coloured export still uses disjoint solids, as required by 3MF.
    c=np.array(g['center_mm'])
    visible_h=trimesh.util.concatenate([sphere(c+d/np.linalg.norm(d)*g['hydrogen_offset_mm'],g['hydrogen_radius_mm'],3)
        for d in np.array(methane()['positions'])[1:]])
    fig=plt.figure(figsize=(16,11),facecolor="#f6f4ef")
    fig.text(.04,.955,"MOLECULAR OBJECTS",fontsize=30,weight="bold",color="#253039")
    fig.text(.04,.917,"DESIGN 01   /   REAL COORDINATES, HANDHELD SCALE",fontsize=11,color="#687277")
    labels=[("[6]HELICENE / MIRROR PAIR","100 mm each · carbon skeleton"),("INFINITENE / (P,P)","140 mm · original paper coordinates"),("CAFFEINE","110 mm · C / N / O"),("MOF-5 + FREE CH4 GUEST","150 mm frame · 27 clusters / 54 linkers")]
    for index,(title,subtitle) in enumerate(labels):
        bottom=.16+(1-index//2)*.385
        ax=fig.add_axes([.025+(index%2)*.49,bottom,.47,.34],projection="3d")
        view=[(180,48,-78,1.45),(145,66,-78,1.55),(120,72,-90,1.4),(175,23,-55,1.1)][index]
        setup_ax(ax,extent=view[0],elev=view[1],azim=view[2],zoom=view[3])
        if index==0:
            hp=data[0][2]*.75;hp[:,0]-=53
            hq=data[1][2]*.75;hq[:,0]+=53
            draw_model(ax,data[0][1],hp,atom_radius=2.6)
            draw_model(ax,data[1][1],hq,atom_radius=2.6,override=COLORS["Zn"])
        elif index==1:draw_model(ax,data[2][1],data[2][2])
        elif index==2:draw_model(ax,data[3][1],data[3][2])
        else:draw_model(ax,m,pts);draw_guest(ax,g)
        finish_scene(ax)
        fig.text(.055+(index%2)*.49,bottom-.012,title,fontsize=15,weight="bold",color="#253039")
        fig.text(.055+(index%2)*.49,bottom-.038,subtitle,fontsize=10,color="#687277")
    fig.text(.04,.04,"C  BLACK     N  BLUE     O  ORANGE*     Zn  GREY     H  WHITE",fontsize=10,color="#253039")
    fig.text(.04,.064,"Grey helicene is also carbon: colour distinguishes the mirror pair. MOF printing prototype uses a uniform grey frame.",fontsize=9,color="#687277")
    fig.text(.04,.018,"*Available-filament palette. H omitted except CH4. Guest size/proportions exaggerated. Design prototype: not sliced or test-printed.",fontsize=9,color="#687277")
    fig.savefig(OUT/"design-overview.png",dpi=180,facecolor=fig.get_facecolor());plt.close(fig)
    # Exact exported geometry: assembled and separated parts.
    fig=plt.figure(figsize=(15,8),facecolor="#f6f4ef")
    fig.text(.04,.94,"MOF-5 / CAPTIVE GUEST",fontsize=27,weight="bold",color="#253039")
    for index,exploded in enumerate([False,True]):
        ax=fig.add_axes([.015+index*.49,.1,.48,.76],projection="3d")
        setup_ax(ax,extent=250 if exploded else 190,elev=20,azim=-55)
        ax.molecular_parts=[]
        for mesh,color,offset in [(lower,"#727d86",np.array([0,0,-20 if exploded else 0])),(upper,"#aab3b9",np.array([0,0,60 if exploded else 0])),(gs[0],COLORS["C"],np.zeros(3)),(visible_h,COLORS["H"],np.zeros(3))]:
            shown=mesh.copy();shown.apply_translation(offset);ax.molecular_parts.append((shown,color))
        finish_scene(ax)
        ax.text2D(.04,0,"ASSEMBLED / FREE GUEST" if not exploded else "EXPLODED / 9 ALIGNMENT JOINTS",transform=ax.transAxes,fontsize=13,weight="bold")
    fig.text(.04,.04,f"Guest clearance >= {g['central_clearance_mm']:.1f} mm  |  Retention margin {g['retention_margin_mm']:.2f} mm  |  Peg 3.0 / socket {MOF_SOCKET_DIAMETER_MM:.1f} mm: coupon-selected; frame untested",fontsize=10)
    fig.savefig(OUT/"mof-assembly.png",dpi=160,facecolor=fig.get_facecolor());plt.close(fig)
    for label,model,p in data:
        fig=plt.figure(figsize=(13,5),facecolor="#f6f4ef")
        fig.text(.03,.95,label.upper()+" / ORTHOGRAPHIC",fontsize=22,weight="bold")
        for i,(elev,azim,title) in enumerate([(90,-90,"TOP"),(0,-90,"FRONT"),(0,0,"SIDE")]):
            ax=fig.add_subplot(1,3,i+1,projection="3d");setup_ax(ax,extent=165,elev=elev,azim=azim)
            draw_model(ax,model,p)
            if label=="mof5":draw_guest(ax,g)
            finish_scene(ax)
            ax.set_title(title,fontsize=10)
        fig.savefig(OUT/(label+"-views.png"),dpi=130,facecolor=fig.get_facecolor());plt.close(fig)
    print('done',flush=True)


if __name__=="__main__":
    if "--render-only" in sys.argv:
        saved=json.loads((OUT/"design-data.json").read_text())
        data=[(name,item["model"],np.array(item["positions_mm"])) for name,item in saved.items()]
        g=json.loads((OUT/"validation.json").read_text())["models"]["mof5"]["guest"]
        c=np.array(g["center_mm"])
        gs=[sphere(c,g["carbon_radius_mm"],3)]
        hs=[sphere(c+d/np.linalg.norm(d)*g["hydrogen_offset_mm"],g["hydrogen_radius_mm"],3) for d in np.array(methane()["positions"])[1:]]
        hydrogen=trimesh.boolean.difference([union(hs),gs[0]],engine="manifold")
        render_design(data,data[-1][1],data[-1][2],g,trimesh.load_mesh(OUT/"mof5_lower.stl"),trimesh.load_mesh(OUT/"mof5_upper.stl"),gs,hydrogen)
    else:build()
