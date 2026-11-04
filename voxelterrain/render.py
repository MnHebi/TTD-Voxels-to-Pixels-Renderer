# SPDX-License-Identifier: GPL-2.0-only
"""Deterministic voxel rasterisation in OpenTTD's screen coordinate system.

World tile: x,y in [0,16], z in normal-zoom screen pixels.
Projection: screen_x=2*(y-x), screen_y=x+y-z. The sampling phase is
intentional: flat coverage is 64x31 at (-31,0), 128x63 at (-62,-1),
and 256x127 at (-124,-2). Never centre a cropped sprite on its image.
"""
from dataclasses import dataclass
import math

import numpy as np
from PIL import Image

from .model import validate
from .palette import PALETTES, RESERVED, quantize, indexed
from .geometry import Geometry, apply_ttd_slope
from .building import BuildingGeometry


@dataclass
class Reference:
    image: Image.Image
    mask: Image.Image | None
    xoffset: int
    yoffset: int
    scale: float = 1
    provenance: dict | None = None
    indexed: bool = True


@dataclass
class Render:
    rgb: Image.Image
    palette_image: Image.Image
    mask: Image.Image
    offset: tuple
    cell_map: np.ndarray
    bounds: dict
    uncovered: int
    clipped: int
    missing_ground: int
    tiling: dict
    tile_map: np.ndarray | None = None


def _raster_triangle(points, cell, normal, buffers, left, top, zoom):
    if normal is None:
        normal=np.cross(points[1]-points[0],points[2]-points[0])
        length=np.linalg.norm(normal)
        if length<1e-10:return
        normal=normal/length
    xy = np.array([[2*(v[1]-v[0]), v[0]+v[1]-v[2]] for v in points])
    # Pixel coordinates corresponding to projected vertices.
    pxy = np.column_stack(((xy[:, 0]+1)*zoom-.5, xy[:, 1]*zoom-1-zoom//2))
    h, w = buffers[0].shape
    x0 = max(0, int(math.floor(pxy[:, 0].min()))-left)
    x1 = min(w, int(math.ceil(pxy[:, 0].max()))-left+1)
    y0 = max(0, int(math.floor(pxy[:, 1].min()))-top)
    y1 = min(h, int(math.ceil(pxy[:, 1].max()))-top+1)
    if x1 <= x0 or y1 <= y0:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1]
    sx = (xx+left+.5)/zoom-1
    sy = (yy+top+1+zoom//2)/zoom
    a, b, c = xy
    det = (b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
    if abs(det) < 1e-10:
        return
    u = ((b[1]-c[1])*(sx-c[0])+(c[0]-b[0])*(sy-c[1]))/det
    v = ((c[1]-a[1])*(sx-c[0])+(a[0]-c[0])*(sy-c[1]))/det
    t = 1-u-v
    inside = (u >= -1e-8) & (v >= -1e-8) & (t >= -1e-8)
    xyz = u[:, :, None]*points[0] + v[:, :, None]*points[1] + t[:, :, None]*points[2]
    depth = xyz[:, :, 0]+xyz[:, :, 1]
    zbuf, positions, normals, cells = buffers
    region = np.s_[y0:y1, x0:x1]
    hit = inside & (depth >= zbuf[region]-1e-8)
    zbuf[region][hit] = depth[hit]
    positions[region][hit] = xyz[hit]
    normals[region][hit] = normal
    cells[region][hit] = cell


def _quad(vertices, cell, normal, buffers, left, top, zoom):
    v = np.array(vertices, dtype=float)
    _raster_triangle(v[[0, 1, 2]], cell, normal, buffers, left, top, zoom)
    _raster_triangle(v[[0, 2, 3]], cell, normal, buffers, left, top, zoom)


def _raster_geometry(geometry, profile, buffers, left, top, zoom):
    n,step=geometry.n,geometry.step
    for i in range(n*n):
        for triangle in geometry.triangles(i):
            _raster_triangle(triangle,i,None,buffers,left,top,zoom)
        x,y=i%n,i//n
        for side in (0,1):
            external=(x==n-1) if side==0 else (y==n-1)
            if external and profile=="ground":continue
            if side==0:
                start=np.array([(x+1)*step,y*step]);end=start+[0,step]
                upper=geometry.corners[i,[1,2]]
                lower=np.zeros(2) if external else geometry.corners[i+1,[0,3]]
            else:
                start=np.array([x*step,(y+1)*step]);end=start+[step,0]
                upper=geometry.corners[i,[3,2]]
                lower=np.zeros(2) if external else geometry.corners[i+n,[0,1]]
            difference=upper-lower
            if difference.max()<=1e-9:continue
            a,b=0.,1.
            if difference.min()<0:
                crossing=float(difference[0]/(difference[0]-difference[1]))
                if difference[0]>0:b=crossing
                else:a=crossing
            pa=start+(end-start)*a;pb=start+(end-start)*b
            za=float(upper[0]+(upper[1]-upper[0])*a)
            zb=float(upper[0]+(upper[1]-upper[0])*b)
            la=float(lower[0]+(lower[1]-lower[0])*a)
            lb=float(lower[0]+(lower[1]-lower[0])*b)
            _quad([(*pa,la),(*pb,lb),(*pb,zb),(*pa,za)],i,
                  (1,0,0) if side==0 else (0,1,0),buffers,left,top,zoom)


def render(project, reference=None, zoom=None):
    p = validate(project)
    s = zoom or p["zoom"]
    n = p["size"]
    building=p["profile"] in ("building","house")
    geometry=BuildingGeometry(p["building"]) if building else Geometry(p)
    native=None
    if p["profile"]=="ground" and p["terrain_slope"] is not None:
        native=Geometry(apply_ttd_slope(dict(p),p["terrain_slope"]))
    maximum=max(geometry.maximum,native.maximum if native else 0)
    left, top = -34*s, -int(math.ceil(maximum+3))*s
    right,bottom=34*s+4,33*s+4
    if building:
        left=-32*geometry.width*s-4*s
        right=32*geometry.depth*s+4*s
        bottom=16*(geometry.width+geometry.depth)*s+4*s
    if p["profile"]=="ground" and native is None and reference is not None:
        ratio=s/reference.scale
        left=min(left,int(math.floor(reference.xoffset*ratio))-2)
        top=min(top,int(math.floor(reference.yoffset*ratio-s//2))-2)
        right=max(right,int(math.ceil((reference.xoffset+reference.image.width)*ratio))+2)
        bottom=max(bottom,int(math.ceil((reference.yoffset+reference.image.height)*ratio))+2)
    w,h=right-left,bottom-top
    if w*h>2_000_000:
        raise ValueError("Ground reference is too large for a single terrain tile; use raised-object placement")
    zbuf = np.full((h, w), -np.inf)
    positions = np.zeros((h, w, 3))
    normals = np.zeros((h, w, 3))
    cells = np.full((h, w), -1, dtype=np.int32)
    buffers = zbuf, positions, normals, cells
    step = 1 if building else geometry.step
    if building:
        for i,triangle,normal in geometry.triangles():
            _raster_triangle(triangle,i,normal,buffers,left,top,s)
    else:
        _raster_geometry(geometry,p["profile"],buffers,left,top,s)
    visible = cells >= 0
    safe_cells = np.maximum(cells, 0)
    materials=([part["colour"] for part in p["building"]["parts"]] or ["#000000"]) if building else p["colours"]
    tags=([part["tag"] for part in p["building"]["parts"]] or [0]) if building else p["tags"]
    colours = np.array([[int(c[k:k+2],16) for k in (1,3,5)] for c in materials], dtype=float)
    base = colours[safe_cells]
    semantic = np.array(tags, dtype=np.uint8)[safe_cells]
    tagged = semantic != 0
    palette = np.array(PALETTES[p["palette"]]).reshape(256,3)
    base[tagged] = palette[semantic[tagged]]
    light = p["light"]
    az, el = math.radians(light["azimuth"]), math.radians(light["elevation"])
    # Ground projection of +x,+y light points to the lower-right at the default.
    sun = np.array([math.cos(az)*math.cos(el), math.sin(az)*math.cos(el), math.sin(el)])
    direct = np.clip((normals*sun).sum(axis=2),0,1)
    shadow = np.zeros((h,w), dtype=bool)
    if light["shadows"] and sun[2] > 0:
        for distance in np.linspace(.6, 24, 24):
            sample = positions + sun*distance
            ix = np.floor(sample[:,:,0]/step).astype(int)
            iy = np.floor(sample[:,:,1]/step).astype(int)
            valid = (ix>=0)&(ix<n)&(iy>=0)&(iy<n)&visible
            if building:
                valid=visible
                occluded=np.zeros((h,w),dtype=bool)
                occluded[valid]=geometry.occupied(sample[valid]+normals[valid]*.02)
                shadow |= occluded
            else:
                terrain = geometry.height(sample[:,:,0],sample[:,:,1])
                shadow |= valid & (terrain > sample[:,:,2]+.15)
    direct[shadow] *= 1-light["shadows"]
    occlusion = np.zeros((h,w))
    if light["ao"]:
        for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
            nx=positions[:,:,0]+dx*step;ny=positions[:,:,1]+dy*step
            valid=(nx>=0)&(nx<16)&(ny>=0)&(ny<16)
            tangent=positions[:,:,2]-(normals[:,:,0]*dx*step+normals[:,:,1]*dy*step)/np.maximum(normals[:,:,2],.01)
            tangent=np.where(normals[:,:,2]>.01,tangent,positions[:,:,2])
            if building:
                points=positions+normals*.2+np.array([dx,dy,.5])
                samples=np.zeros((h,w),dtype=bool)
                samples[visible]=geometry.occupied(points[visible])
                occlusion+=samples*.25
            else:
                above=geometry.height(nx,ny)-tangent
                occlusion += np.clip(above/4,0,1)*valid*.25
    illumination = np.clip((light["ambient"]+light["strength"]*direct)*(1-light["ao"]*occlusion),0,2)
    rgb = base*illumination[:,:,None]
    # OpenTTD's mask channel uses 128 as neutral brightness, not the
    # brightness of the blue/animated palette swatch itself.
    mask_brightness=128*illumination
    uncovered = 0
    if p["texture"] != "none":
        if reference is None:
            raise ValueError("Select a reference sprite before enabling a texture")
        src = np.asarray(reference.image.convert("RGBA"))
        sx = 2*(positions[:,:,1]-positions[:,:,0])
        sy = positions[:,:,0]+positions[:,:,1]
        if p["texture"] == "project":
            sy -= positions[:,:,2]
        rs = reference.scale
        tx = np.floor((sx+1)*rs-reference.xoffset).astype(int)
        ty = np.floor(sy*rs-1-int(rs)//2-reference.yoffset+.5).astype(int)
        ok = (tx>=0)&(tx<src.shape[1])&(ty>=0)&(ty<src.shape[0])&visible
        txc,tyc=np.clip(tx,0,src.shape[1]-1),np.clip(ty,0,src.shape[0]-1)
        ok &= src[tyc,txc,3]>0
        tex = src[tyc,txc,:3].astype(float)
        factor = (1-p["texture_light"])+p["texture_light"]*illumination
        rgb[ok] = (tex*factor[:,:,None])[ok]
        if reference.mask is not None:
            indices = np.asarray(reference.mask)
            sampled = indices[tyc,txc]
            special = (np.isin(sampled,list(RESERVED[p["palette"]]-{0})) if reference.indexed else sampled!=0) & ok
            semantic[ok] = 0
            semantic[special] = sampled[special]
            if reference.indexed:
                source_brightness=np.full(src.shape[:2],128)
            else:
                source_brightness=src[:,:,:3].max(axis=2).astype(float)
                source_brightness[source_brightness==0]=128
            mask_brightness[special]=(source_brightness[tyc,txc]*factor)[special]
        uncovered = int((visible & ~ok).sum())
    rgba = np.concatenate([np.clip(rgb,0,255).astype(np.uint8), (visible*255).astype(np.uint8)[:,:,None]],axis=2)
    clipped = 0
    missing_ground = 0
    if p["profile"] == "ground":
        yy,xx=np.mgrid[:h,:w]
        px,py=xx+left,yy+top
        sx=(px+.5)/s-1
        sy=(py+1+s//2)/s
        wx=(sy-sx/2)/2
        wy=(sy+sx/2)/2
        flat_mask=(wx>=0)&(wx<16)&(wy>=0)&(wy<16)
        if native is not None:
            native_buffers=(np.full((h,w),-np.inf),np.zeros((h,w,3)),np.zeros((h,w,3)),np.full((h,w),-1,dtype=np.int32))
            _raster_geometry(native,"ground",native_buffers,left,top,s)
            mask=native_buffers[3]>=0
        elif reference is not None:
            # A ground reference defines the permitted silhouette, never its image centre.
            src=np.asarray(reference.image.convert("RGBA"))
            # Recognise the flat silhouette by pixels, not by a sprite name/ID.
            flat_reference=False
            if reference.scale==1 and reference.image.size==(64,31) and (reference.xoffset,reference.yoffset)==(-31,0):
                ry0,rx0=np.mgrid[:31,:64]
                sx0=rx0-31-.5;sy0=ry0+1
                fx=(sy0-sx0/2)/2;fy=(sy0+sx0/2)/2
                expected=(fx>=0)&(fx<16)&(fy>=0)&(fy<16)
                flat_reference=np.array_equal(src[:,:,3]>0,expected)
            if flat_reference:
                # Smooth extra-zoom edges use the engine sampling phase, not a
                # nearest-neighbour enlargement of a 31-row normal sprite.
                mask=flat_mask
            else:
                ratio=s/reference.scale
                origin_x=reference.xoffset*ratio
                origin_y=reference.yoffset*ratio-s//2+int(reference.scale)//2*ratio
                rx=np.floor((px-origin_x)/ratio).astype(int)
                ry=np.floor((py-origin_y)/ratio).astype(int)
                valid=(rx>=0)&(rx<src.shape[1])&(ry>=0)&(ry<src.shape[0])
                mask=valid & (src[np.clip(ry,0,src.shape[0]-1),np.clip(rx,0,src.shape[1]-1),3]>0)
        else:
            # Flat-tile contract. Raised geometry is deliberately clipped at the ground boundary.
            mask=flat_mask
        clipped=int((visible & ~mask).sum())
        missing_ground=int((mask & ~visible).sum())
        rgba[~mask,3]=0
        visible &= mask
    rgba[~visible] = 0
    semantic[~visible] = 0
    cells[~visible] = -1
    image=Image.fromarray(rgba)
    box=image.getbbox()
    if box is None:
        if not building:
            raise ValueError("The model has no visible pixels inside the export footprint")
        box=(0,0,1,1)
    image=image.crop(box)
    x0,y0,x1,y1=box
    tags=semantic[y0:y1,x0:x1]
    pal=quantize(image,p["palette"],p["dither"],tags,p["palette_mapping"])
    mask=indexed(tags,p["palette"])
    # Masked RGB pixels encode brightness; do not feed blue hue into recolouring.
    rgb_arr=np.array(image)
    special=tags!=0
    if special.any():
        intensity=np.clip(mask_brightness[y0:y1,x0:x1],1,255).astype(np.uint8)
        rgb_arr[special,:3]=intensity[special,None]
    image=Image.fromarray(rgb_arr)
    bounds={"xoffset":0,"yoffset":0,"zoffset":0,"xextent":16*(geometry.width if building else 1),"yextent":16*(geometry.depth if building else 1),
            "zextent":max(1,int(math.ceil(geometry.maximum)))}
    tile_map=None
    if building:
        xyz=positions[y0:y1,x0:x1]
        tx=np.clip(np.floor((xyz[:,:,0]-1e-8)/16).astype(int),0,geometry.width-1)
        ty=np.clip(np.floor((xyz[:,:,1]-1e-8)/16).astype(int),0,geometry.depth-1)
        tile_map=ty*geometry.width+tx
        tile_map[~visible[y0:y1,x0:x1]]=-1
    tiling={"compatible":False,"delta_x":0,"delta_y":0,"edge_error_x":0,"edge_error_y":0} if building else geometry.tiling()
    return Render(image,pal,mask,(left+x0,top+y0),cells[y0:y1,x0:x1],bounds,uncovered,clipped,missing_ground,tiling,tile_map)


def building_fragments(result, building, zoom):
    """Disjoint visible-pixel fragments, each anchored to its own north tile corner.

    Split after scene lighting/quantisation so assembly exactly reproduces the render.
    No invented walls are drawn through a roof at an internal tile boundary.
    """
    width,depth=BuildingGeometry(building).width,BuildingGeometry(building).depth
    fragments=[]
    for y in range(depth):
        for x in range(width):
            keep=result.tile_map==y*width+x
            box=Image.fromarray((keep*255).astype(np.uint8)).getbbox()
            if box is None:box=(0,0,1,1)
            images=[]
            for source in (result.rgb,result.palette_image,result.mask):
                arr=np.array(source)
                arr[~keep]=0
                im=Image.frombytes(source.mode,source.size,arr.tobytes())
                if source.mode=="P":
                    im.putpalette(source.getpalette());im.info["transparency"]=0
                images.append(im.crop(box))
            bounds={"xoffset":0,"yoffset":0,"zoffset":0,"xextent":16,"yextent":16,"zextent":result.bounds["zextent"]}
            fragment=Render(*images,(result.offset[0]+box[0]-32*(y-x)*zoom,
                                    result.offset[1]+box[1]-16*(x+y)*zoom),
                            result.cell_map[box[1]:box[3],box[0]:box[2]],bounds,0,0,0,result.tiling)
            fragments.append((x,y,fragment))
    return fragments
