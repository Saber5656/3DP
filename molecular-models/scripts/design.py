"""Molecular coordinates and millimetre design geometry. No printer control."""
from __future__ import annotations

import copy
import itertools
import re
from collections import Counter
from pathlib import Path

import gemmi
import numpy as np
from rdkit import Chem
from rdkit.Chem import rdMolDescriptors
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components


def load_sdf(path):
    mol = Chem.SDMolSupplier(str(path), removeHs=False)[0]
    if mol is None:
        raise ValueError(f"Cannot parse {path}")
    formula = rdMolDescriptors.CalcMolFormula(mol)
    mol = Chem.RemoveHs(mol)
    return dict(name=Path(path).stem, formula=formula,
                elements=[a.GetSymbol() for a in mol.GetAtoms()],
                positions=mol.GetConformer().GetPositions().tolist(),
                bonds=[[b.GetBeginAtomIdx(), b.GetEndAtomIdx()] for b in mol.GetBonds()],
                bond_orders=[b.GetBondTypeAsDouble() for b in mol.GetBonds()],
                coordinates="PubChem computed 3D conformer; explicit H omitted from display")


def mirror(model):
    out = copy.deepcopy(model)
    p = np.array(out["positions"])
    p[:, 0] *= -1
    out["positions"] = p.tolist()
    out["name"] += "_mirror"
    return out


def load_infinitene(root):
    text = (Path(root) / "ja1c10807_si_001.txt").read_text()
    text = text.split("8. Cartesian coordinates of optimized structures")[-1]
    text = text.split("(P,P)-1", 1)[1].split("(M,M)-1", 1)[0]
    rows = re.findall(r"^([CH])\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)", text, re.M)
    if Counter(r[0] for r in rows) != {"C":48,"H":24}:
        raise ValueError("Unexpected infinitene coordinate block")
    xyz = "72\n(P,P)-infinitene; original paper SI p. S23; PBE0/6-311+G(d,p); angstrom\n"
    xyz += "\n".join(" ".join(row) for row in rows)+"\n"
    (Path(root)/"infinitene.xyz").write_text(xyz)
    p=np.array([[float(x) for x in row[1:]] for row in rows if row[0]=="C"])
    bonds=sorted(cKDTree(p).query_pairs(1.75))
    return dict(name="infinitene",formula="C48H24",elements=["C"]*48,
                positions=p.tolist(),bonds=[list(b) for b in bonds],
                coordinates="Original 2022 JACS SI p. S23, (P,P)-1, PBE0/6-311+G(d,p)")


def components(n, pairs):
    if len(pairs)==0: return np.arange(n)
    pairs=np.asarray(pairs)
    g=coo_matrix((np.ones(2*len(pairs)),(np.r_[pairs[:,0],pairs[:,1]],np.r_[pairs[:,1],pairs[:,0]])),shape=(n,n))
    return connected_components(g,directed=False)[1]


def build_mof(path,cells=2):
    s=gemmi.read_small_structure(str(path))
    sites=s.get_all_unit_cell_sites()
    counts=dict(Counter(a.element.name for a in sites))
    a=s.cell.a
    centers=np.array(list(itertools.product(range(cells+1),repeat=3)))*a/2+a/4
    elements=[];names=[];positions=[]
    for shift in itertools.product(range(-1,cells+1),repeat=3):
        for site in sites:
            if site.element.name=="H":continue
            f=np.array([site.fract.x,site.fract.y,site.fract.z])+shift
            p=f*a
            if np.all(p>=centers.min(0)-3.3) and np.all(p<=centers.max(0)+3.3):
                elements.append(site.element.name);names.append(site.label);positions.append(p)
    p=np.array(positions)
    # No duplicate atom identities after symmetry expansion and periodic tiling.
    keys=[(e,*np.round(v,6)) for e,v in zip(elements,p)]
    unique=list(dict.fromkeys(keys));lookup={k:i for i,k in enumerate(keys)}
    idx=[lookup[k] for k in unique]
    p=p[idx];elements=np.array(elements)[idx];names=np.array(names)[idx]
    all_pairs=[]
    for i,j in sorted(cKDTree(p).query_pairs(2.3)):
        d=np.linalg.norm(p[i]-p[j]);pair={elements[i],elements[j]}
        if (pair <= {"C","O"} and pair!={"O"} and 1.1<d<1.8) or (pair=={"Zn","O"} and 1.5<d<2.3):
            all_pairs.append((i,j))
    organic_pairs=[(i,j) for i,j in all_pairs if elements[i]!="Zn" and elements[j]!="Zn"]
    labels=components(len(p),organic_pairs)
    selected=set()
    for i,(name,elem) in enumerate(zip(names,elements)):
        if elem=="Zn" or name=="O1":
            if np.min(np.linalg.norm(centers-p[i],axis=1))<2.01:selected.add(i)
    linkers=[]
    for label in set(labels):
        members=np.flatnonzero(labels==label)
        if Counter(elements[members])!={"C":8,"O":4}:continue
        metals=set()
        for i,j in all_pairs:
            if i in members and j in selected and elements[j]=="Zn":metals.add(j)
            if j in members and i in selected and elements[i]=="Zn":metals.add(i)
        if len(metals)!=4:continue
        clusters=set(np.argmin(np.linalg.norm(centers-p[k],axis=1)) for k in metals)
        if len(clusters)==2:
            selected.update(members.tolist());linkers.append(members.tolist())
    kept=sorted(selected);mapping={i:j for j,i in enumerate(kept)}
    bonds=[[mapping[i],mapping[j]] for i,j in all_pairs if i in selected and j in selected]
    return dict(name="mof5",formula="Zn4O(BDC)3 periodic framework; finite cutout",
                elements=elements[kept].tolist(),positions=p[kept].tolist(),bonds=bonds,
                cluster_count=len(centers),linker_count=len(linkers),unit_cell_counts=counts,
                cluster_centers=centers.tolist(),cell_a_angstrom=a,
                coordinates="RASPA2 IRMOF-1 CIF, expanded Fm-3m symmetry; terminal links truncated; H omitted")


def orient(model):
    p=np.array(model["positions"])
    if model["name"].startswith("mof"):return p-p.mean(0)
    p=p-p.mean(0)
    _,_,vt=np.linalg.svd(p,full_matrices=False)
    if np.linalg.det(vt)<0:vt[-1]*=-1
    return p@vt.T


def scaled_positions(model,width,atom_radius=3.2):
    p=orient(model)
    scale=(width-2*atom_radius)/np.ptp(p,axis=0).max()
    return p*scale,scale


def methane():
    xyz=np.array([[0,0,0],[1,1,1],[1,-1,-1],[-1,1,-1],[-1,-1,1]],float)
    xyz[1:]*=1.09/np.sqrt(3)
    return dict(name="methane",formula="CH4",elements=["C","H","H","H","H"],
                positions=xyz.tolist(),bonds=[[0,i] for i in range(1,5)],
                coordinates="Ideal tetrahedral geometry, C-H 1.09 angstrom; explanatory guest")


def clearance(points,positions,elements,bonds,bond_radius=1.65):
    """Signed distance to union of ideal atom balls and bond capsules, in mm."""
    points=np.atleast_2d(points);positions=np.asarray(positions)
    radii=np.array([2.7 if e=="Zn" else 2.2 for e in elements])
    value=np.full(len(points),np.inf)
    for start in range(0,len(positions),128):
        ds=np.linalg.norm(points[:,None,:]-positions[None,start:start+128,:],axis=2)-radii[None,start:start+128]
        value=np.minimum(value,ds.min(1))
    for i,j in bonds:
        x=positions[i];v=positions[j]-x
        t=np.clip((points-x)@v/np.dot(v,v),0,1)
        value=np.minimum(value,np.linalg.norm(points-(x+t[:,None]*v),axis=1)-bond_radius)
    return value


def analyze_guest(model,positions,scale):
    # Every route out of the cutout crosses this closed six-face box.
    c=(np.array(model["cluster_centers"])-np.array(model["positions"]).mean(0))*scale
    lo=c.min(0);hi=c.max(0)
    step=0.65
    axes=[np.linspace(lo[d],hi[d],int(np.ceil((hi[d]-lo[d])/step))+1) for d in range(3)]
    maxima=[];spacing=[]
    for d in range(3):
        other=[x for x in range(3) if x!=d]
        grid=np.array(list(itertools.product(axes[other[0]],axes[other[1]])))
        spacing.append(np.hypot(axes[other[0]][1]-axes[other[0]][0],axes[other[1]][1]-axes[other[1]][0])/2)
        for bound in (lo[d],hi[d]):
            pts=np.zeros((len(grid),3));pts[:,d]=bound;pts[:,other]=grid
            vals=[]
            for chunk in np.array_split(pts,max(1,int(np.ceil(len(pts)/2048)))):
                vals.extend(clearance(chunk,positions,model["elements"],model["bonds"]))
            maxima.append(float(np.max(vals)))
    upper=max(maxima)+max(spacing)
    # Centre of the first of 2x2x2 pores, not the centre of the complete model.
    # The overall box centre is an occupied Zn4O node, so it must not be used.
    # Select halfway between the first two node coordinates along each axis.
    center=np.array([(np.unique(c[:,d])[0]+np.unique(c[:,d])[1])/2 for d in range(3)])
    available=float(clearance([center],positions,model["elements"],model["bonds"])[0])
    carbon_radius=upper+1.25
    # Retention uses a sphere INSIDE the guest: if this carbon core cannot cross
    # any boundary face, the larger methane body cannot cross either, at any rotation.
    # Collision-free fitting uses a sphere OUTSIDE the entire methane body: if it
    # fits at the chosen pore centre, all guest rotations fit there as well.
    h_radius=carbon_radius*0.46
    h_offset=carbon_radius*0.76
    outer=max(carbon_radius,h_radius+h_offset)
    return dict(center_mm=center.tolist(),carbon_radius_mm=carbon_radius,
                hydrogen_radius_mm=h_radius,hydrogen_offset_mm=h_offset,
                guest_outer_radius_mm=outer,cavity_inscribed_radius_mm=available,
                central_clearance_mm=available-outer,
                aperture_radius_upper_bound_mm=upper,aperture_sampled_max_mm=max(maxima),
                grid_cover_error_bound_mm=max(spacing),retention_margin_mm=carbon_radius-upper,
                method="Six boundary faces, exact analytic ball/capsule distances, 1-Lipschitz grid cover bound; rigid ideal geometry only",
                guest_representation="CH4 space-filling display, enlarged vs host, ball proportions stylized; not van der Waals radii")
