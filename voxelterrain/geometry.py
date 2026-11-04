# SPDX-License-Identifier: GPL-2.0-only
"""Solid columns with piecewise-planar caps and OpenTTD terrain slope profiles.

Corner order: N=(0,0), W=(1,0), S=(1,1), E=(0,1).
Slope bits and continuous planes follow OpenTTD slope_type.h / landscape.cpp.
"""
import numpy as np

SHAPES = {
    "cube": (0, 0, 0, 0),
    "wedge": (1, 0, 0, 1),
    "diagonal": (1, .5, 0, .5),
    "corner": (1, 0, 0, 0),
    "inner_corner": (1, 1, 0, 1),
    "ridge": (1, 0, 1, 0),
    "valley": (1, 0, 1, 0),
    "pyramid": (0, 0, 0, 0),
}
SHAPE_LABELS = {"cube":"Cube / flat", "wedge":"Wedge", "diagonal":"Diagonal ramp",
                "corner":"Outer corner", "inner_corner":"Inner corner", "ridge":"Ridge",
                "valley":"Valley", "pyramid":"Pyramid"}
SLOPE_NAMES = {0:"Flat", 1:"Corner W", 2:"Corner S", 3:"Ramp SW", 4:"Corner E", 5:"Valley EW",
               6:"Ramp SE", 7:"Three corners WSE", 8:"Corner N", 9:"Ramp NW", 10:"Valley NS",
               11:"Three corners NWS", 12:"Ramp NE", 13:"Three corners ENW", 14:"Three corners SEN",
               23:"Steep S", 27:"Steep W", 29:"Steep N", 30:"Steep E"}
SLOPE_OFFSETS = {**{i:i for i in range(15)}, 29:15, 23:16, 27:17, 30:18}


def ttd_height(slope, x, y):
    """Continuous terrain plane, before the engine's integer sampling rounding."""
    x,y=np.broadcast_arrays(np.asarray(x,dtype=float),np.asarray(y,dtype=float))
    if slope==0:return np.zeros_like(x)
    if slope==1:return np.maximum((x-y)/2,0)
    if slope==2:return np.maximum((x+y-16)/2,0)
    if slope==4:return np.maximum((y-x)/2,0)
    if slope==8:return np.maximum((16-x-y)/2,0)
    if slope==3:return x/2
    if slope==6:return y/2
    if slope==9:return (16-y)/2
    if slope==12:return (16-x)/2
    if slope==7:return 8-np.maximum((16-x-y)/2,0)
    if slope==11:return 8-np.maximum((y-x)/2,0)
    if slope==13:return 8-np.maximum((x+y-16)/2,0)
    if slope==14:return 8-np.maximum((x-y)/2,0)
    if slope==5:return np.abs(x-y)/2
    if slope==10:return np.abs(16-x-y)/2
    if slope==23:return (x+y)/2
    if slope==27:return (16+x-y)/2
    if slope==29:return (32-x-y)/2
    if slope==30:return (16+y-x)/2
    raise ValueError("Unsupported TTD slope")


def diagonal_02(shape, rotation):
    if shape in ("corner","inner_corner","valley"):
        return rotation%2==1
    if shape=="ridge":
        return rotation%2==0
    return True


class Geometry:
    def __init__(self, project):
        self.n=project["size"]
        self.step=16/self.n
        self.base=np.array(project["heights"],dtype=float)
        self.rise=np.array(project["rises"],dtype=float)
        self.pyramids=np.array([s=="pyramid" for s in project["shapes"]])
        self.diagonal=np.array([diagonal_02(s,r) for s,r in zip(project["shapes"],project["rotations"])])
        profiles=np.array([np.roll(SHAPES[s],-r) for s,r in zip(project["shapes"],project["rotations"])])
        self.corners=self.base[:,None]+self.rise[:,None]*profiles
        self.maximum=float(max(self.corners.max(),(self.base+self.rise*self.pyramids).max()))

    def height(self,x,y):
        x,y=np.broadcast_arrays(np.asarray(x),np.asarray(y))
        ix=np.clip(np.floor(x/self.step).astype(int),0,self.n-1)
        iy=np.clip(np.floor(y/self.step).astype(int),0,self.n-1)
        i=iy*self.n+ix
        u=np.clip(x/self.step-ix,0,1);v=np.clip(y/self.step-iy,0,1)
        a,b,c,d=np.moveaxis(self.corners[i],-1,0)
        along02=np.where(u>=v,a+(b-a)*u+(c-b)*v,a+(c-d)*u+(d-a)*v)
        along13=np.where(u+v<=1,a+(b-a)*u+(d-a)*v,c+(d-c)*(1-u)+(b-c)*(1-v))
        surface=np.where(self.diagonal[i],along02,along13)
        pyramid=self.base[i]+self.rise[i]*(1-2*np.maximum(np.abs(u-.5),np.abs(v-.5)))
        return np.where(self.pyramids[i],pyramid,surface)

    def triangles(self,i):
        x,y=i%self.n,i//self.n
        x0,y0=x*self.step,y*self.step
        x1,y1=x0+self.step,y0+self.step
        a,b,c,d=self.corners[i]
        vertices=np.array([(x0,y0,a),(x1,y0,b),(x1,y1,c),(x0,y1,d)])
        if self.pyramids[i]:
            center=np.array([x0+self.step/2,y0+self.step/2,self.base[i]+self.rise[i]])
            for j in range(4):yield np.array([vertices[j],vertices[(j+1)%4],center])
        elif self.diagonal[i]:
            yield vertices[[0,1,2]]
            yield vertices[[0,2,3]]
        else:
            yield vertices[[0,1,3]]
            yield vertices[[1,2,3]]

    def tiling(self):
        samples=np.linspace(0,16,self.n*4+1)
        dx=self.height(np.full_like(samples,16),samples)-self.height(np.zeros_like(samples),samples)
        dy=self.height(samples,np.full_like(samples,16))-self.height(samples,np.zeros_like(samples))
        x_error=float(np.max(np.abs(dx-dx[0])))
        y_error=float(np.max(np.abs(dy-dy[0])))
        return {"compatible":x_error<1e-8 and y_error<1e-8,"delta_x":float(dx[0]),"delta_y":float(dy[0]),
                "edge_error_x":x_error,"edge_error_y":y_error}


def apply_ttd_slope(project, slope):
    """Tessellate a whole terrain tile into editable, adjoining cap shapes."""
    if type(slope) is not int or slope not in SLOPE_NAMES:
        raise ValueError("Unsupported TTD slope")
    n=project["size"];step=16/n
    heights=[];shapes=[];rotations=[];rises=[]
    for y in range(n):
        for x in range(n):
            points=np.array([(x,y),(x+1,y),(x+1,y+1),(x,y+1)])*step
            corners=ttd_height(slope,points[:,0],points[:,1])
            base=float(corners.min());rise=float(corners.max()-base)
            found=None
            if rise<1e-9:
                found=("cube",0)
            else:
                profile=(corners-base)/rise
                for shape in ("wedge","diagonal","corner","inner_corner","valley"):
                    for rotation in range(4):
                        if np.allclose(profile,np.roll(SHAPES[shape],-rotation),atol=1e-9):
                            found=(shape,rotation)
                            break
                    if found:break
            if found is None:
                raise ValueError("Terrain slope cannot be represented at this grid size")
            heights.append(base);rises.append(rise);shapes.append(found[0]);rotations.append(found[1])
    project.update(heights=heights,shapes=shapes,rotations=rotations,rises=rises,terrain_slope=slope)
    return project
