# SPDX-License-Identifier: GPL-2.0-only
"""TTD palettes and quantisation which never invents special colour indices."""
import json
from pathlib import Path

import numpy as np
from PIL import Image

PALETTES = json.loads((Path(__file__).resolve().parent.parent / "assets/palettes.json").read_text())
# DOS: company blue 198..205, unused pink 215..226, animation 227..254.
# Windows reserves 1..9, 246..255; company blue 198..205 and animation 217..244.
RESERVED = {"dos": {0, *range(198, 206), *range(215, 256)},
            "windows": {*range(0, 10), *range(198, 206), *range(217, 256)}}
COMPANY = tuple(range(198, 206))


def indexed(array, palette="dos"):
    image = Image.fromarray(np.asarray(array, dtype=np.uint8))
    image = image.convert("P")
    image.putpalette(PALETTES[palette])
    image.info["transparency"] = 0
    return image


def oklab(rgb):
    """sRGB bytes to OKLab, using Bjorn Ottosson's public-domain matrices."""
    c=np.asarray(rgb,dtype=float)/255
    linear=np.where(c<=.04045,c/12.92,((c+.055)/1.055)**2.4)
    lms=linear@np.array([[.4122214708,.5363325363,.0514459929],
                         [.2119034982,.6806995451,.1073969566],
                         [.0883024619,.2817188376,.6299787005]]).T
    return np.cbrt(lms)@np.array([[.2104542553,.7936177850,-.0040720468],
                                  [1.9779984951,-2.4285922050,.4505937099],
                                  [.0259040371,.7827717662,-.8086757660]]).T


def balanced_indices(rgb, colours, allowed, dither):
    """Constrain chromatic colours by hue, neutrals by chroma, then match in OKLab.

    Ordered two-colour mixtures use only the same eligible family. This improves
    local tone balance without shifting noise across green/yellow boundaries.
    """
    unique,inv,counts=np.unique(rgb.reshape(-1,3),axis=0,return_inverse=True,return_counts=True)
    representatives=unique;bins=None
    if len(unique)>32768:
        # Bound photo work to a 5-bit histogram. Representatives are frequency-
        # weighted source colours, preserving dominant tones rather than bin centres.
        keys=((unique[:,0]//8)*1024+(unique[:,1]//8)*32+unique[:,2]//8)
        _,bins=np.unique(keys,return_inverse=True)
        population=np.bincount(bins,weights=counts)
        representatives=np.column_stack([np.bincount(bins,weights=unique[:,j]*counts)/population for j in range(3)])
    target=oklab(representatives);pal=oklab(colours[allowed])
    pc=np.linalg.norm(pal[:,1:],axis=1);ph=np.arctan2(pal[:,2],pal[:,1])
    first=np.empty(len(target),dtype=np.uint8);second=first.copy();mix=np.zeros(len(target))
    weights=np.array([1.5,1.8,1.8])
    for start in range(0,len(target),1024):
        lab=target[start:start+1024];c=np.linalg.norm(lab[:,1:],axis=1)
        hue=np.arctan2(lab[:,2],lab[:,1])
        delta=np.abs(np.angle(np.exp(1j*(hue[:,None]-ph))))
        chromatic=(c>=.035)&(lab[:,0]>=.2)
        similar=(pc[None,:]>=.025)&(delta<=np.deg2rad(15))
        # If the palette has no close hue, retain its nearest available hue family.
        nearest=np.where(pc[None,:]>=.025,delta,np.inf).min(axis=1)
        similar|=(pc[None,:]>=.025)&(delta<=nearest[:,None]+np.deg2rad(3))
        eligible=np.where(chromatic[:,None],similar,True)
        neutral=c<.025
        eligible[neutral]=(pc<.012)&(np.ptp(colours[allowed],axis=1)<=4)
        diff=(lab[:,None,:]-pal[None,:,:])*weights
        score=np.sum(diff*diff,axis=2)
        score[~eligible]=np.inf
        a=score.argmin(axis=1);b=a.copy();ratio=np.zeros(len(lab))
        if dither:
            base=pal[a];direction=(pal[None,:,:]-base[:,None,:])*weights
            residual=(lab-base)*weights
            norm=np.sum(direction*direction,axis=2)
            t=np.clip(np.sum(residual[:,None,:]*direction,axis=2)/np.maximum(norm,1e-20),0,1)
            error=np.sum((residual[:,None,:]-t[:,:,None]*direction)**2,axis=2)
            error[~eligible]=np.inf
            b=error.argmin(axis=1);ratio=t[np.arange(len(lab)),b]
        end=start+len(lab);first[start:end]=allowed[a];second[start:end]=allowed[b];mix[start:end]=ratio
    if bins is not None:first,second,mix=first[bins],second[bins],mix[bins]
    # Exact ordinary game-palette colours remain exact, including in large photos.
    packed=unique[:,0]*65536+unique[:,1]*256+unique[:,2]
    pcodes=colours[allowed,0]*65536+colours[allowed,1]*256+colours[allowed,2]
    positions=np.searchsorted(packed,pcodes)
    exact=(positions<len(packed))&(packed[np.minimum(positions,len(packed)-1)]==pcodes)
    first[positions[exact]]=allowed[exact];second[positions[exact]]=allowed[exact];mix[positions[exact]]=0
    chosen=first[inv].reshape(rgb.shape[:2])
    if dither:
        bayer=np.array([[0,8,2,10],[12,4,14,6],[3,11,1,9],[15,7,13,5]])
        threshold=np.tile((bayer+.5)/16,((rgb.shape[0]+3)//4,(rgb.shape[1]+3)//4))[:rgb.shape[0],:rgb.shape[1]]
        chosen=np.where(threshold<mix[inv].reshape(chosen.shape),second[inv].reshape(chosen.shape),chosen).astype(np.uint8)
    return chosen


def quantize(rgba, palette="dos", dither=False, semantic=None, mapping="nearest"):
    """Opaque pixels get ordinary colours unless explicitly tagged as special."""
    src = np.asarray(rgba, dtype=np.uint8)
    if mapping not in ("nearest","balanced"):
        raise ValueError("Unknown palette mapping")
    colours = np.array(PALETTES[palette], dtype=np.int32).reshape(256, 3)
    allowed = np.array([i for i in range(256) if i not in RESERVED[palette]])
    rgb = src[:, :, :3].astype(np.int32)
    if dither and mapping=="nearest":
        bayer = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]])
        noise = np.tile(bayer, ((rgb.shape[0]+3)//4, (rgb.shape[1]+3)//4))[:rgb.shape[0], :rgb.shape[1]]
        rgb = np.clip(rgb + (noise[:, :, None] - 7.5)*1.5, 0, 255).astype(np.int32)
    if mapping=="balanced":
        result=balanced_indices(rgb,colours,allowed,dither)
    else:
        unique, inv = np.unique(rgb.reshape(-1, 3), axis=0, return_inverse=True)
        chosen = np.empty(len(unique), dtype=np.uint8)
        for start in range(0, len(unique), 2048):
            delta = unique[start:start+2048, None, :] - colours[allowed][None, :, :]
            chosen[start:start+2048] = allowed[(delta*delta).sum(axis=2).argmin(axis=1)]
        result = chosen[inv].reshape(src.shape[:2])
    if semantic is not None:
        tagged = np.asarray(semantic, dtype=np.uint8)
        result[tagged != 0] = tagged[tagged != 0]
    result[src[:, :, 3] < 128] = 0
    return indexed(result, palette)


def display_masked_rgba(image, mask, palette="dos"):
    """Display the mask using OpenTTD's 128-neutral brightness semantics.

    Uses the same integer channel scaling and overbright redistribution as
    OpenTTD palette.cpp ReallyAdjustBrightness (GPL-2.0-or-later).
    """
    rgba=np.array(image)
    tags=np.asarray(mask)
    special=tags!=0
    if not special.any():
        return image
    brightness=rgba[:,:,:3].max(axis=2)[special].astype(np.int32)
    brightness[brightness==0]=128
    colours=np.array(PALETTES[palette],dtype=np.int32).reshape(256,3)[tags[special]]
    scaled=colours*brightness[:,None]//128
    over=np.maximum(scaled-255,0).sum(axis=1)//2
    adjusted=np.where(scaled>=255,255,scaled+over[:,None]*(255-scaled)//256)
    rgba[special,:3]=np.clip(adjusted,0,255).astype(np.uint8)
    return Image.fromarray(rgba)
