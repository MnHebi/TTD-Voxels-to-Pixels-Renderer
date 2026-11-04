# SPDX-License-Identifier: GPL-2.0-only
"""Editable solid building parts, independent of the terrain heightfield."""
import copy
import math
import re

import numpy as np

PART_SHAPES = {"box": "Box / floor / wall", "gable": "Gable roof", "hip": "Hip roof", "shed": "Shed roof"}
BUILDING_PRESETS = {"cottage": "Cottage", "townhouse": "Town house", "office": "Office", "warehouse": "Warehouse", "empty": "Empty lot"}


def default_building():
    return {"width": 1, "depth": 1, "parts": [], "view": 0, "views": 4,
            "stage": 3, "population": 40, "mail": 8, "passenger_acceptance": 4,
            "mail_acceptance": 2, "probability": 1, "year_from": 1850, "year_to": 65535}


def validate_building(data):
    if not isinstance(data, dict):
        raise ValueError("Invalid building model")
    b = {**default_building(), **copy.deepcopy(data)}
    for key, lo, hi in (("width",1,2),("depth",1,2),("view",0,3),("stage",0,3),
                        ("population",0,255),("mail",0,255),("passenger_acceptance",0,8),
                        ("mail_acceptance",0,8),("year_from",0,65535),("year_to",0,65535)):
        if type(b[key]) is not int or not lo <= b[key] <= hi:
            raise ValueError(f"Building {key} must be an integer {lo}..{hi}")
    if b["views"] not in (1,4) or type(b["views"]) is not int:
        raise ValueError("Export one or four building views")
    if not isinstance(b["probability"], (int,float)) or not math.isfinite(b["probability"]) or not 0 < b["probability"] <= 15:
        raise ValueError("Town growth probability must be greater than 0 and at most 15")
    if b["year_to"] < b["year_from"]:
        raise ValueError("Last construction year must follow the first")
    if not isinstance(b["parts"],list) or len(b["parts"]) > 160:
        raise ValueError("A building supports up to 160 parts")
    parts=[]
    for raw in b["parts"]:
        if not isinstance(raw,dict):raise ValueError("Invalid building part")
        p={"name":"Part","shape":"box","x":2,"y":2,"z":0,"width":12,"depth":12,"height":8,
           "colour":"#c4b69a","tag":0,"rotation":0,"visible":True,**raw}
        if p["shape"] not in PART_SHAPES:raise ValueError("Unsupported building part shape")
        for key in ("x","y","z","width","depth","height"):
            try:v=float(p[key])
            except (ValueError,TypeError):raise ValueError(f"Invalid part {key}") from None
            if not math.isfinite(v) or not 0 <= v <= 128:raise ValueError(f"Part {key} must be 0..128")
            p[key]=v
        if min(p["width"],p["depth"],p["height"]) < .125:
            raise ValueError("Part dimensions must be at least 0.125 game units")
        if p["x"]+p["width"]>b["width"]*16 or p["y"]+p["depth"]>b["depth"]*16:
            raise ValueError("Part extends beyond the building lot; enlarge the footprint or move the part")
        if p["z"]+p["height"]>128:raise ValueError("Building top must not exceed 128 game pixels")
        if type(p["rotation"]) is not int or p["rotation"] not in (0,1):raise ValueError("Roof axis must be 0 or 1")
        if type(p["tag"]) is not int or not 0<=p["tag"]<=255:raise ValueError("Invalid part palette effect")
        if not isinstance(p["colour"],str) or not re.fullmatch(r"#[0-9a-fA-F]{6}",p["colour"]):raise ValueError("Part colour must be #RRGGBB")
        if type(p["visible"]) is not bool:raise ValueError("Invalid part visibility")
        p["name"]=str(p["name"])[:60];parts.append(p)
    b["parts"]=parts
    return b


def part(name,x,y,z,w,d,h,colour,shape="box",rotation=0):
    return dict(name=name,x=x,y=y,z=z,width=w,depth=d,height=h,colour=colour,shape=shape,rotation=rotation,tag=0,visible=True)


def building_preset(project, kind):
    if kind not in BUILDING_PRESETS:raise ValueError("Unknown building preset")
    p=copy.deepcopy(project);b=default_building();parts=[]
    if kind=="warehouse":b.update(width=2,depth=2,population=12)
    if kind=="townhouse":b.update(width=1,depth=2,population=90)
    w,d=16*b["width"],16*b["depth"]
    if kind!="empty":
        parts.append(part("Paved foundation",.5,.5,0,w-1,d-1,1,"#898778"))
        height={"cottage":10,"townhouse":26,"office":44,"warehouse":14}[kind]
        wall="#d7c6a6" if kind!="warehouse" else "#a19079"
        parts.append(part("Main walls",2,2,1,w-4,d-4,height,wall))
        parts.append(part("Roof",1.5,1.5,1+height,w-3,d-3,6 if kind!="office" else 2,
                          "#a95840" if kind!="office" else "#66747a",
                          "gable" if kind in ("cottage","warehouse") else "hip" if kind=="townhouse" else "box"))
        # Thin solid facade details can be edited independently like any other part.
        floors=1 if kind in ("cottage","warehouse") else 3 if kind=="townhouse" else 5
        for floor in range(floors):
            z=3+floor*(height/floors)
            for x in np.arange(4,w-4,4):parts.append(part(f"Front window {floor+1}/{int(x)}",float(x),d-1.85,z,2,.25,3,"#546f78"))
            for y in np.arange(4,d-4,4):parts.append(part(f"Side window {floor+1}/{int(y)}",w-1.85,float(y),z,.25,2,3,"#546f78"))
        parts.append(part("Door",w/2-1,d-1.75,1,2,.25,6,"#544638"))
        if kind=="cottage":parts.append(part("Chimney",5,5,13,2,2,7,"#807367"))
        if kind=="office":parts.append(part("Roof plant",5,5,47,4,4,3,"#9dada9"))
    b["parts"]=parts
    p.update(profile="building",terrain_slope=None,name=BUILDING_PRESETS[kind],building=validate_building(b),texture="none")
    return p


def rotate_xy(points, width, depth, view):
    q=np.array(points,dtype=float,copy=True)
    for _ in range(view):
        x=q[...,0].copy();q[...,0]=depth-q[...,1];q[...,1]=x
        width,depth=depth,width
    return q


def footprint(building, view=None):
    view=building["view"] if view is None else view
    return (building["depth"],building["width"]) if view%2 else (building["width"],building["depth"])


def _roof_mesh(p):
    """Return a closed upward cap plus its four side faces, in local XY."""
    shape=p["shape"]
    vertices=[[0,0,1 if shape=="box" else 0],[1,0,1 if shape=="box" else 0],
              [1,1,1 if shape=="box" else 0],[0,1,1 if shape=="box" else 0]]
    if shape=="box":faces=[[0,1,2],[0,2,3]]
    elif shape=="shed":
        vertices=[[0,0,0],[1,0,1],[1,1,1],[0,1,0]];faces=[[0,1,2],[0,2,3]]
    elif shape=="gable":
        vertices += [[.5,0,1],[.5,1,1]]
        faces=[[0,4,5],[0,5,3],[4,1,2],[4,2,5]]
    else:
        # A hip has a level ridge; its ends are half the short side from the ends.
        w,d=p["width"],p["depth"]
        if p["rotation"]:w,d=d,w
        if w>=d:
            t=d/(2*w);vertices += [[t,.5,1],[1-t,.5,1]]
            faces=[[0,1,5],[0,5,4],[1,2,5],[2,3,4],[2,4,5],[3,0,4]]
        else:
            t=w/(2*d);vertices += [[.5,t,1],[.5,1-t,1]]
            faces=[[0,1,4],[1,2,5],[1,5,4],[2,3,5],[3,0,4],[3,4,5]]
    v=np.array(vertices,dtype=float)
    if p["rotation"]:v[:,:2]=v[:,[1,0]]
    return v,faces


class BuildingGeometry:
    def __init__(self, building, view=None, stage=None):
        self.building=building
        self.view=building["view"] if view is None else view
        self.stage=building["stage"] if stage is None else stage
        self.width,self.depth=footprint(building,self.view)
        self.maximum=max([p["z"]+p["height"] for p in building["parts"] if p["visible"]] or [1])
        self.cutoff=self.maximum*(.2,.45,.7,1)[self.stage]
        self.maximum=min(self.maximum,self.cutoff)

    def triangles(self):
        b=self.building
        for i,p in enumerate(b["parts"]):
            if not p["visible"] or p["z"]>=self.cutoff:continue
            v,faces=_roof_mesh(p)
            v[:,0]=p["x"]+v[:,0]*p["width"];v[:,1]=p["y"]+v[:,1]*p["depth"]
            v[:,2]=p["z"]+v[:,2]*p["height"]
            triangles=[]
            for face in faces:
                for above in (False,True):
                    polygon=[]
                    for a,c in zip(v[face],np.roll(v[face],-1,axis=0)):
                        ina=a[2]>=self.cutoff if above else a[2]<=self.cutoff
                        inc=c[2]>=self.cutoff if above else c[2]<=self.cutoff
                        if ina:polygon.append(a.copy())
                        if ina!=inc:polygon.append(a+(c-a)*((self.cutoff-a[2])/(c[2]-a[2])))
                    if above:
                        for vertex in polygon:vertex[2]=self.cutoff
                    for j in range(1,len(polygon)-1):triangles.append(np.array([polygon[0],polygon[j],polygon[j+1]]))
            # Include midpoint roof vertices on boundary walls (gable ends).
            for axis,bound in ((0,p["x"]),(0,p["x"]+p["width"]),(1,p["y"]),(1,p["y"]+p["depth"])):
                edge=v[np.isclose(v[:,axis],bound)]
                edge=edge[np.argsort(edge[:,1-axis])]
                for a,c in zip(edge[:-1],edge[1:]):
                    segment=[a.copy()]
                    if (a[2]<self.cutoff<c[2]) or (c[2]<self.cutoff<a[2]):segment.append(a+(c-a)*((self.cutoff-a[2])/(c[2]-a[2])))
                    segment.append(c.copy())
                    for a,c in zip(segment[:-1],segment[1:]):
                        a[2]=min(a[2],self.cutoff);c[2]=min(c[2],self.cutoff)
                        lo=a.copy();lo[2]=p["z"];lc=c.copy();lc[2]=p["z"]
                        triangles.extend([np.array([lo,lc,c]),np.array([lo,c,a])])
            for triangle in triangles:
                q=rotate_xy(triangle,16*b["width"],16*b["depth"],self.view)
                normal=np.cross(q[1]-q[0],q[2]-q[0]);length=np.linalg.norm(normal)
                if length<1e-9:continue
                normal/=length
                # Side wall winding is chosen explicitly by its outward direction.
                if np.ptp(q[:,2])>1e-9 and (np.ptp(q[:,0])<1e-9 or np.ptp(q[:,1])<1e-9):
                    center=rotate_xy([[p["x"]+p["width"]/2,p["y"]+p["depth"]/2,0]],16*b["width"],16*b["depth"],self.view)[0]
                    if np.dot(normal[:2],q.mean(axis=0)[:2]-center[:2])<0:normal=-normal
                elif normal[2]<0:normal=-normal
                # Camera ray points towards increasing X,Y and decreasing Z.
                if normal[0]+normal[1]+2*normal[2]<=1e-9:continue
                yield i,q,normal

    def occupied(self, points):
        # Query actual solids, including empty space beneath raised roofs/floors.
        b=self.building
        q=rotate_xy(points,16*self.width,16*self.depth,(4-self.view)%4)
        out=np.zeros(q.shape[:-1],dtype=bool)
        for p in b["parts"]:
            if not p["visible"] or p["z"]>=self.cutoff:continue
            hit=(q[...,0]>=p["x"])&(q[...,0]<=p["x"]+p["width"])&(q[...,1]>=p["y"])&(q[...,1]<=p["y"]+p["depth"])&(q[...,2]>=p["z"])&(q[...,2]<=min(p["z"]+p["height"],self.cutoff))
            if not hit.any():continue
            u=(q[...,0][hit]-p["x"])/p["width"];v=(q[...,1][hit]-p["y"])/p["depth"]
            if p["rotation"]:u,v=v,u
            if p["shape"]=="box":cap=np.ones_like(u)
            elif p["shape"]=="shed":cap=u
            elif p["shape"]=="gable":cap=1-np.abs(2*u-1)
            else:
                w,d=p["width"],p["depth"]
                if p["rotation"]:w,d=d,w
                short=min(w,d)
                cap=np.minimum.reduce([2*u*w/short,2*(1-u)*w/short,2*v*d/short,2*(1-v)*d/short,np.ones_like(u)])
            inside=q[...,2][hit]<=p["z"]+p["height"]*cap+1e-8
            out[hit]|=inside
        return out
