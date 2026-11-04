# SPDX-License-Identifier: GPL-2.0-only
"""Normalised screenshot references and game-palette conversions."""
import base64
import hashlib
import io

from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError

from .palette import quantize, PALETTES

MAX_PICTURE_BYTES=24*1024*1024
MAX_PICTURE_PIXELS=16_000_000
MAX_PICTURE_EDGE=1600


def png_bytes(image):
    out=io.BytesIO();image.save(out,format="PNG");return out.getvalue()


def import_picture(payload, name="Reference picture"):
    if not payload or len(payload)>MAX_PICTURE_BYTES:
        raise ValueError("Reference pictures must be at most 24 MiB")
    try:
        source=Image.open(io.BytesIO(payload))
        if source.format not in ("PNG","JPEG","WEBP","BMP","GIF"):
            raise ValueError("Choose PNG, JPEG, WebP, BMP or GIF")
        if source.width*source.height>MAX_PICTURE_PIXELS:
            raise ValueError("Reference pictures must be at most 16 million pixels")
        source.seek(0);source=ImageOps.exif_transpose(source)
        original=source.size
        alpha=source.convert("RGBA").getchannel("A")
        profile=source.info.get("icc_profile")
        if profile:
            try:
                image=ImageCms.profileToProfile(source if source.mode in ("RGB","CMYK","LAB") else source.convert("RGB"),
                                               ImageCms.ImageCmsProfile(io.BytesIO(profile)),
                                               ImageCms.createProfile("sRGB"),outputMode="RGB")
            except (ImageCms.PyCMSError,ValueError,OSError) as exc:
                raise ValueError("The picture's colour profile could not be converted to sRGB") from exc
            image=image.convert("RGBA");image.putalpha(alpha)
        else:image=source.convert("RGBA")
        image.thumbnail((MAX_PICTURE_EDGE,MAX_PICTURE_EDGE),Image.Resampling.LANCZOS)
        # A reference copy is sRGB with orientation applied; exclude source metadata.
        clean=Image.frombytes("RGBA",image.size,image.tobytes())
        data=png_bytes(clean)
        return {"name":str(name)[:120],"png":base64.b64encode(data).decode("ascii"),
                "width":clean.width,"height":clean.height,"original_width":original[0],"original_height":original[1],
                "sha256":hashlib.sha256(payload).hexdigest(),"resized":clean.size!=original}
    except (UnidentifiedImageError,Image.DecompressionBombError,OSError) as exc:
        raise ValueError("Cannot read this reference picture") from exc


def picture_image(png):
    if not isinstance(png,str) or len(png)>32*1024*1024:
        raise ValueError("Reference picture data is too large")
    try:
        image=Image.open(io.BytesIO(base64.b64decode(png,validate=True)))
        if image.format!="PNG" or max(image.size)>MAX_PICTURE_EDGE:
            raise ValueError("Import the picture before converting it")
        image.load();return image.convert("RGBA")
    except (UnidentifiedImageError,OSError,base64.binascii.Error) as exc:
        raise ValueError("Invalid reference picture PNG") from exc


def convert_picture(png, palette="dos", mapping="balanced", dither=True):
    if palette not in PALETTES:raise ValueError("Unknown game palette")
    image=picture_image(png)
    return quantize(image,palette,bool(dither),mapping=mapping)


def validate_pictures(pictures):
    if not isinstance(pictures,list) or len(pictures)>12:
        raise ValueError("A reference window supports up to 12 pictures")
    if any(not isinstance(p,dict) or not isinstance(p.get("png"),str) for p in pictures):
        raise ValueError("Invalid reference picture")
    if sum(len(p["png"]) for p in pictures)>64*1024*1024:
        raise ValueError("Reference pictures exceed the 64 MiB project limit")
    output=[]
    for p in pictures:
        if not isinstance(p,dict):raise ValueError("Invalid reference picture")
        image=picture_image(p.get("png"))
        # Keep only fields used by the viewer; derive dimensions from the image.
        output.append({"name":str(p.get("name","Reference picture"))[:120],"png":p["png"],
                       "width":image.width,"height":image.height,
                       "original_width":p.get("original_width",image.width),"original_height":p.get("original_height",image.height),
                       "resized":bool(p.get("resized",False)),"sha256":str(p.get("sha256",""))[:64]})
    return output
