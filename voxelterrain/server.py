# SPDX-License-Identifier: GPL-2.0-only
"""Loopback-only UI server. No cloud services, uploads or telemetry."""
import base64
import io
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import traceback
from urllib.parse import urlsplit, parse_qs

from PIL import Image

from .export import export_bundle, compiler_available
from .grf import ROOT, MAX_UPLOAD, MAX_SPRITE_PIXELS, codec_path, import_grf, export_references
from .model import default_project, validate, preset, resize
from .geometry import SHAPE_LABELS, SLOPE_NAMES, SLOPE_OFFSETS
from .building import PART_SHAPES, BUILDING_PRESETS
from .palette import PALETTES, RESERVED, display_masked_rgba
from .render import Reference, render
from .pictures import import_picture, convert_picture, validate_pictures, MAX_PICTURE_BYTES


def png_data(image):
    out=io.BytesIO()
    image.save(out,format="PNG")
    return base64.b64encode(out.getvalue()).decode("ascii")


def decode_png(data):
    if not isinstance(data,str) or len(data)>12_000_000:
        raise ValueError("Reference image is too large")
    raw=base64.b64decode(data,validate=True)
    image=Image.open(io.BytesIO(raw))
    if image.format!="PNG" or image.width*image.height>MAX_SPRITE_PIXELS:
        raise ValueError("Invalid reference PNG")
    image.load()
    return image


def resolve_reference(project):
    r=project.get("reference")
    if r is None:
        return None
    if r.get("palette")!=project["palette"] and project["texture"]!="none":
        raise ValueError("Texture and project palettes must match. Re-import with the desired palette or use reference-only mode.")
    scale=r.get("scale",1)
    if scale not in (.125,.25,.5,1,2,4):
        raise ValueError("Invalid reference zoom")
    dx,dy=r.get("xoffset"),r.get("yoffset")
    if type(dx) is not int or type(dy) is not int or not -32768<=dx<=32767 or not -32768<=dy<=32767:
        raise ValueError("Invalid reference origin")
    image=decode_png(r.get("png"))
    mask=decode_png(r["mask"]) if r.get("mask") else None
    if mask is not None and (mask.mode!="P" or mask.size!=image.size):
        raise ValueError("Reference mask must be indexed and match its image")
    provenance={k:r.get(k) for k in ("source","sha256","sprite","depth","zoom","palette")}
    return Reference(image.convert("RGBA"),mask,dx,dy,scale,provenance,indexed=r.get("depth")=="8bpp")


def sample_reference(project, x, y):
    """Sample original pixels and palette indices, never thumbnail/background RGB."""
    ref=resolve_reference(project)
    if ref is None:
        raise ValueError("Select a reference sprite to sample")
    if type(x) is not int or type(y) is not int or not 0<=x<ref.image.width or not 0<=y<ref.image.height:
        raise ValueError("Sample coordinates are outside the reference sprite")
    rgba=ref.image.getpixel((x,y))
    index=ref.mask.getpixel((x,y)) if ref.mask is not None else 0
    effect=index if index and (not ref.indexed or index in RESERVED[project["reference"]["palette"]]) else 0
    return {"colour":"#"+"".join(f"{v:02x}" for v in rgba[:3]),"alpha":rgba[3],
            "index":index if ref.indexed or index else None,"tag":effect,
            "palette":project["reference"]["palette"]}


class Workshop(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,address):
        super().__init__(address,Handler)
        self.token=secrets.token_urlsafe(32)
        self.libraries={}
        self.import_lock=threading.Lock()
        self.compute_lock=threading.Lock()
        self.picture_lock=threading.Lock()


class Handler(BaseHTTPRequestHandler):
    server: Workshop
    def log_message(self,*args):
        pass

    def respond(self,content,status=200,mime="application/json",filename=None):
        if isinstance(content,(dict,list)):
            content=json.dumps(content,ensure_ascii=False).encode()
        elif isinstance(content,str):
            content=content.encode()
        self.send_response(status)
        self.send_header("Content-Type",mime+"; charset=utf-8" if mime.startswith("text/") or mime=="application/json" else mime)
        self.send_header("Content-Length",str(len(content)))
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Cache-Control","no-store")
        self.send_header("Content-Security-Policy","default-src 'self'; img-src 'self' data: blob:; style-src 'self'; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        if filename:
            self.send_header("Content-Disposition",f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(content)

    def check_host(self):
        return self.headers.get("Host") in (f"127.0.0.1:{self.server.server_port}",f"localhost:{self.server.server_port}")

    def do_GET(self):
        try:
            if not self.check_host():
                return self.respond({"error":"Invalid host"},403)
            parsed=urlsplit(self.path)
            q=parse_qs(parsed.query)
            if parsed.path=="/favicon.ico":
                self.respond(b"",status=204,mime="image/x-icon")
            elif parsed.path=="/api/bootstrap":
                try:
                    codec_path()
                    codec=True
                except ValueError:
                    codec=False
                self.respond({"project":default_project(),"token":self.server.token,"palettes":PALETTES,
                              "reserved":{k:sorted(v) for k,v in RESERVED.items()},
                              "codec":codec,"compiler":compiler_available(),"shapes":SHAPE_LABELS,
                              "terrain_slopes":SLOPE_NAMES,"slope_offsets":SLOPE_OFFSETS,
                              "building_shapes":PART_SHAPES,"building_presets":BUILDING_PRESETS})
            elif parsed.path=="/api/library":
                lib=self.server.libraries[q["id"][0]]
                search=q.get("q",[""])[0].strip()
                candidates=lib.sprites
                if search:
                    candidates=[s for s in candidates if search in str(s.number)]
                if q.get("tiles",["false"])[0]=="true":
                    candidates=[s for s in candidates if s.width>=48 and s.height>=20 and s.width<=300 and s.height<=160]
                offset=max(0,int(q.get("offset",["0"])[0]))
                self.respond({"name":lib.name,"total":len(candidates),"all":len(lib.sprites),"offset":offset,
                              "sprites":[s.public() for s in candidates[offset:offset+60]]})
            elif parsed.path in ("/api/sprite","/api/reference"):
                lib=self.server.libraries[q["id"][0]]
                key=int(q["key"][0])
                image,mask=lib.crop(key)
                s=lib.get(key)
                if parsed.path=="/api/reference":
                    scales={"normal":1,"zi2":2,"zi4":4,"zo2":.5,"zo4":.25,"zo8":.125}
                    self.respond({"png":png_data(image),"mask":png_data(mask) if mask else None,
                                  "xoffset":s.xoffset,"yoffset":s.yoffset,"scale":scales[s.zoom],
                                  "source":lib.name,"sha256":lib.digest,"sprite":s.number,
                                  "depth":s.depth,"zoom":s.zoom,"palette":lib.palette})
                else:
                    out=io.BytesIO()
                    image.save(out,format="PNG")
                    self.respond(out.getvalue(),mime="image/png",filename="reference.png" if "download" in q else None)
            else:
                files={"/":"index.html","/app.js":"app.js","/pictures.js":"pictures.js","/style.css":"style.css"}
                if parsed.path not in files:
                    return self.respond({"error":"Not found"},404)
                path=ROOT/"web"/files[parsed.path]
                self.respond(path.read_bytes(),mime={".html":"text/html",".js":"text/javascript",".css":"text/css"}[path.suffix])
        except (ValueError,KeyError,IndexError,TypeError) as exc:
            self.respond({"error":str(exc)},400)
        except Exception:
            traceback.print_exc()
            self.respond({"error":"Request failed; see the server console for details"},500)

    def do_POST(self):
        try:
            if not self.check_host() or not secrets.compare_digest(self.headers.get("X-Workshop-Token",""),self.server.token):
                return self.respond({"error":"Invalid request token; reload the workshop"},403)
            origin=self.headers.get("Origin")
            if origin and origin not in (f"http://127.0.0.1:{self.server.server_port}",f"http://localhost:{self.server.server_port}"):
                return self.respond({"error":"Invalid request origin"},403)
            size=int(self.headers.get("Content-Length","0"))
            path=urlsplit(self.path).path
            limit=MAX_UPLOAD if path=="/api/import" else 72*1024*1024 if path=="/api/pictures/validate" else MAX_PICTURE_BYTES if path=="/api/pictures/import" else 32*1024*1024
            if not 0<size<=limit:
                return self.respond({"error":"Request size exceeds the limit"},413)
            body=self.rfile.read(size)
            if path=="/api/pictures/import":
                q=parse_qs(urlsplit(self.path).query)
                return self.respond(import_picture(body,q.get("name",["Reference picture"])[0]))
            if path=="/api/import":
                q=parse_qs(urlsplit(self.path).query)
                with self.server.import_lock:
                    if len(self.server.libraries)>=8:
                        raise ValueError("Eight GRFs are already open. Save your project and restart to free import memory.")
                    requested=q.get("palette",["auto"])[0]
                    lib=import_grf(body,q.get("name",["import.grf"])[0],requested)
                    self.server.libraries[lib.id]=lib
                return self.respond({"id":lib.id,"name":lib.name,"count":len(lib.sprites),"palette":lib.palette,
                                     "declared":lib.declared,"inferred":lib.inferred,"requested":requested})
            data=json.loads(body)
            if path=="/api/pictures/convert":
                with self.server.picture_lock:
                    image=convert_picture(data["png"],data.get("palette","dos"),data.get("mapping","balanced"),data.get("dither",True))
                self.respond({"png":png_data(image),"width":image.width,"height":image.height})
            elif path=="/api/pictures/validate":
                self.respond(validate_pictures(data))
            elif path=="/api/render":
                p=validate(data)
                with self.server.compute_lock:
                    r=render(p,resolve_reference(p))
                image=r.palette_image.convert("RGBA") if p["colour_mode"]=="8bpp" else r.rgb
                # Display company pixels in their source palette for a useful editor preview.
                if p["colour_mode"]!="8bpp":
                    image=display_masked_rgba(image,r.mask,p["palette"])
                self.respond({"png":png_data(image),"palette_png":png_data(r.palette_image),
                              "sample_indices_png":png_data(Image.frombytes("L",image.size,(r.palette_image if p["colour_mode"]=="8bpp" else r.mask).tobytes())),
                              "mask_png":png_data(r.mask),"width":image.width,"height":image.height,
                              "offset":r.offset,"bounds":r.bounds,"cells":r.cell_map.flatten().tolist(),
                              "uncovered":r.uncovered,"clipped":r.clipped,"missing_ground":r.missing_ground,"tiling":r.tiling,
                              "footprint":[r.bounds["xextent"]//16,r.bounds["yextent"]//16]})
            elif path=="/api/preset":
                self.respond(preset(data["project"],data["kind"]))
            elif path=="/api/sample-reference":
                self.respond(sample_reference(validate(data["project"]),data.get("x"),data.get("y")))
            elif path=="/api/resize":
                self.respond(resize(data["project"],data["size"]))
            elif path=="/api/export":
                with self.server.compute_lock:
                    output,manifest,directory=export_bundle(data["projects"],resolve_reference,bool(data.get("build")),bool(data.get("legacy")))
                self.respond(output,mime="application/zip",filename="voxel-terrain-sprites.zip")
            elif path=="/api/validate":
                p=validate(data)
                resolve_reference(p)
                self.respond(p)
            elif path=="/api/export-references":
                lib=self.server.libraries[data["library"]]
                with self.server.compute_lock:
                    output=export_references(lib,data.get("key"))
                self.respond(output,mime="application/zip",filename="grf-reference-sprites.zip")
            else:
                self.respond({"error":"Not found"},404)
        except (ValueError,KeyError,IndexError,TypeError,base64.binascii.Error) as exc:
            self.respond({"error":str(exc)},400)
        except Exception:
            traceback.print_exc()
            self.respond({"error":"Operation failed; see the server console for details"},500)
