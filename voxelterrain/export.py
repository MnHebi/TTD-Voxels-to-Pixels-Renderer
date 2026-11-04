# SPDX-License-Identifier: GPL-2.0-only
"""Individual PNGs, reproducible NML/NFO and optional compiled test NewGRFs."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid
import zipfile

import numpy as np

from .grf import ROOT, WORK, codec_path
from .model import validate, replacement_target
from . import __version__
from .render import render
from .runtime import FROZEN, run_tool

ZOOMS = {1:("normal","ZOOM_LEVEL_NORMAL"),2:("zi2","ZOOM_LEVEL_IN_2X"),4:("zi4","ZOOM_LEVEL_IN_4X")}


def compiler_available():
    return importlib.util.find_spec("nml") is not None or (WORK/"compiler/nml/main.py").exists()


def compile_nml(directory, stem="workshop"):
    if not compiler_available():
        raise ValueError("NML compiler is unavailable. Install requirements.txt to build a test GRF.")
    env = os.environ.copy()
    bundled = WORK/"compiler"
    env["PYTHONPATH"] = os.pathsep.join([str(bundled),env.get("PYTHONPATH","")])
    command=[sys.executable,"--compile-nml"] if FROZEN else [sys.executable,"-m","nml.main"]
    result = subprocess.run([*command,"--no-cache","--grf",f"{stem}.grf",
                             "--nfo",f"{stem}.nfo",f"{stem}.nml"],cwd=directory,env=env,
                            capture_output=True,timeout=120,
                            creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    if result.returncode:
        raise ValueError("NML compilation failed: "+result.stderr.decode("utf-8",errors="replace")[-2400:])
    return result.stderr.decode("utf-8",errors="replace")


def _entry(record, mask=False):
    w,h=record["width"],record["height"]
    dx,dy=record["xoffset"],record["yoffset"]
    filename=record["file"]
    extra=f', "{record["mask"]}"' if mask and record.get("mask") else ""
    return f'[0, 0, {w}, {h}, {dx}, {dy}, NOCROP, "{filename}"{extra}]'


def export_bundle(projects, resolve_reference, build=False, legacy=False):
    if not isinstance(projects,list) or not 1 <= len(projects) <= 64:
        raise ValueError("Export between 1 and 64 tiles")
    projects=[validate(p) for p in projects]
    if len({p["palette"] for p in projects}) != 1:
        raise ValueError("A bundle must use one palette. Export DOS and Windows tiles separately.")
    if legacy and any(p["profile"] != "ground" for p in projects):
        raise ValueError("Legacy export supports ground replacements only; new objects require OpenTTD.")
    targets=[replacement_target(p) for p in projects if p["profile"]=="ground"]
    if any(t>4895 for t in targets):
        raise ValueError("Base sprite replacements must be 0..4895. NewGRF-local sprite numbers are not base sprite IDs.")
    if len(set(targets)) != len(targets):
        raise ValueError("Ground tiles in a bundle must have different replacement sprite IDs.")
    directory=WORK/"exports"/uuid.uuid4().hex
    sprites_dir=directory/"sprites"
    sprites_dir.mkdir(parents=True)
    (directory/"lang").mkdir()
    name="Voxel Terrain Workshop"
    # Project-specific GRFID prevents different exported sets sharing one hard-coded ID.
    digest=hashlib.sha256(json.dumps(projects,sort_keys=True).encode()).digest()
    grfid="VT"+digest[:2].hex().upper()
    grfid_nml="VT"+"".join(f"\\{v:02X}" for v in digest[:2])
    nml=[f'grf {{ grfid: "{grfid_nml}"; name: string(STR_GRF_NAME); desc: string(STR_GRF_DESC); version: 1; min_compatible_version: 1; }}']
    lang=["##grflangid 0x01",f"STR_GRF_NAME :{name}","STR_GRF_DESC :Voxel terrain and building sprite export", "STR_CLASS :Voxel terrain"]
    lang.append("STR_BUILDING_CLASS :Voxel buildings")
    if any(p["profile"]=="house" for p in projects):nml.append("cargotable { PASS, MAIL }")
    manifest={"schema":1,"tool":f"Voxel Terrain Workshop {__version__}","created_utc":datetime.now(timezone.utc).isoformat(),
              "projection":"sx=2*(y-x); sy=x+y-z; north tile corner origin",
              "palette":projects[0]["palette"],"sprites":[],"tiles":[],
              "runtime_status":"NOT_TESTED_IN_GAME","compiled":False,"legacy":legacy}
    for tile_index,p in enumerate(projects):
        ref=resolve_reference(p)
        slug=re.sub(r"[^a-z0-9]+","_",p["name"].lower()).strip("_") or "tile"
        stem=f"{tile_index:03d}_{slug}"
        if p["profile"] in ("building","house"):
            from .building_export import export_building
            export_building(p,ref,directory,tile_index,stem,manifest,nml,lang,_entry)
            continue
        records={}
        # NML and the GRF specification require a normal-zoom 8bpp fallback.
        zooms=[1] if legacy else sorted({1,*p["export_zooms"]})
        for zoom in zooms:
            r=render(p,ref,zoom)
            if r.missing_ground:
                raise ValueError(f'{p["name"]}: {r.missing_ground} ground-footprint pixels have no surface at {zoom}x. Lower the boundary columns, use a matching ground reference, or export as a raised tile object.')
            if legacy or p["colour_mode"]=="8bpp":
                modes=["8bpp"]
            elif p["colour_mode"]=="both" or zoom==1:
                modes=["8bpp","32bpp"]
            else:
                modes=["32bpp"]
            for mode in modes:
                file=f"sprites/{stem}_{zoom}x_{mode}.png"
                image=r.palette_image if mode=="8bpp" else r.rgb
                image.save(directory/file,transparency=0 if mode=="8bpp" else None)
                record={"tile":tile_index,"name":p["name"],"file":file,"mode":mode,"zoom":zoom,
                        "width":image.width,"height":image.height,"xoffset":r.offset[0],"yoffset":r.offset[1],
                        "sha256":hashlib.sha256((directory/file).read_bytes()).hexdigest(),
                        "fallback":p["colour_mode"]=="32bpp" and mode=="8bpp",
                        "untextured_pixels":r.uncovered,"clipped_pixels":r.clipped,
                        "missing_ground_pixels":r.missing_ground}
                if mode=="32bpp" and np.any(np.asarray(r.mask)):
                    maskfile=f"sprites/{stem}_{zoom}x_mask.png"
                    r.mask.save(directory/maskfile,transparency=0)
                    record["mask"]=maskfile
                    record["mask_sha256"]=hashlib.sha256((directory/maskfile).read_bytes()).hexdigest()
                manifest["sprites"].append(record)
                records[zoom,mode]=record
        base=records[1,"8bpp"]
        block=f"tile_{tile_index}"
        if p["profile"]=="ground":
            nml.append(f'replace {block}({replacement_target(p)}) {{ {_entry(base)} }}')
        else:
            nml.append(f'spriteset({block}) {{ {_entry(base)} }}')
        for (zoom,mode),record in records.items():
            if zoom==1 and mode=="8bpp":
                continue
            nml.append(f'alternative_sprites({block}, {ZOOMS[zoom][1]}, BIT_DEPTH_{mode.upper()}) {{ {_entry(record,mode=="32bpp")} }}')
        if p["profile"]=="object":
            zextent=r.bounds["zextent"]
            # The complete tile is solid terrain, so a full footprint is intentional.
            nml.append(f'''spritelayout layout_{tile_index} {{
    ground {{ sprite: GROUNDSPRITE_NORMAL; }}
    building {{ sprite: {block}; zextent: {zextent}; recolour_mode: RECOLOUR_REMAP; palette: PALETTE_USE_DEFAULT; }}
}}
switch(FEAT_OBJECTS, SELF, location_{tile_index}, getbits(extra_callback_info1, 0, 5)) {{
    SLOPE_FLAT: return CB_RESULT_LOCATION_ALLOW;
    return CB_RESULT_LOCATION_DISALLOW;
}}
item(FEAT_OBJECTS, object_{tile_index}) {{
    property {{ class: "VXTW"; classname: string(STR_CLASS); name: string(STR_TILE_{tile_index});
        climates_available: ALL_CLIMATES; size: [1,1]; build_cost_multiplier: 1; remove_cost_multiplier: 1;
        introduction_date: date(0,1,1); end_of_life_date: date(5000000,1,1); height: {math.ceil(zextent/8)}; num_views: 1; }}
    graphics {{ default: layout_{tile_index}; purchase: layout_{tile_index}; tile_check: location_{tile_index}; }}
}}''')
            safe_name=p["name"].replace("\n"," ").replace("\r"," ").replace("{", "(").replace("}", ")")
            lang.append(f"STR_TILE_{tile_index} :{safe_name}")
        manifest["tiles"].append({"name":p["name"],"profile":p["profile"],
                                  "palette_mapping":p["palette_mapping"],
                                  "replacement_id":replacement_target(p) if p["profile"]=="ground" else None,
                                  "terrain_slope":p["terrain_slope"],"terrain_base":p["terrain_base"],
                                  "shapes":sorted(set(p["shapes"])),
                                  "tiling":r.tiling,
                                  "sorting_bounds":r.bounds if p["profile"]=="object" else None,
                                  "reference":ref.provenance if ref else None})
    (directory/"workshop.nml").write_text("\n\n".join(nml)+"\n",encoding="utf-8")
    (directory/"lang/english.lng").write_text("\n".join(lang)+"\n",encoding="utf-8")
    if legacy:
        lines=["// Voxel Terrain Workshop export", "// (Info version 32)",
               "// Format: spritenum imagefile depth xpos ypos xsize ysize xrel yrel zoom flags"]
        def pseudo(payload):
            lines.append(f"{len(lines)-3} * {len(payload)} "+payload.hex(" ").upper())
        # First four-byte pseudo is the number of following records, patched below.
        pseudo(b"\0\0\0\0")
        pal=b"D" if projects[0]["palette"]=="dos" else b"W"
        pseudo(b"\x14CINFOBPALS\x01\0"+pal+b"\0\0")
        pseudo(b"\x08\x07VT"+digest[:2]+b"Voxel terrain\0Ground sprite replacement\0")
        for i,p in enumerate(projects):
            pseudo(bytes([10,1,1])+replacement_target(p).to_bytes(2,"little"))
            rec=next(r for r in manifest["sprites"] if r["tile"]==i)
            lines.append(f'{len(lines)-3} {rec["file"]} 8bpp 0 0 {rec["width"]} {rec["height"]} {rec["xoffset"]} {rec["yoffset"]} normal nocrop')
        lines[3]=f"0 * 4 "+(len(lines)-4).to_bytes(4,"little").hex(" ").upper()
        (directory/"workshop.nfo").write_text("\n".join(lines)+"\n")
        if build:
            codec=codec_path()
            result=run_tool([codec,"-s","-e","-g","1",str(directory/"workshop.grf"),str(directory)],
                                  cwd=directory,capture_output=True,timeout=120,
                                  creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
            if result.returncode:
                raise ValueError("GRFCodec encoding failed: "+(result.stderr+result.stdout).decode(errors="replace")[-1800:])
    elif build:
        compile_nml(directory)
    manifest["compiled"]=build
    manifest["grfid"]=grfid
    if build:
        manifest["grf_sha256"]=hashlib.sha256((directory/"workshop.grf").read_bytes()).hexdigest()
    (directory/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    (directory/"project.voxel.json").write_text(json.dumps({"format":"voxel-terrain-workshop","version":1,"current":projects[0],"tiles":projects},indent=2),encoding="utf-8")
    (directory/"README.txt").write_text("""Voxel Terrain Workshop export

Each sprite is a separate PNG. manifest.json gives exact image bounds,
offsets, hashes and object sorting bounds. Indexed PNGs use transparency index 0.
32bpp-only colour mode includes a normal 8bpp fallback for compatibility.

Build modern exports: nmlc --grf workshop.grf workshop.nml
Build legacy exports: grfcodec -e -g 1 workshop.grf .
Use the command appropriate to this bundle's manifest 'legacy' value.
workshop.grf is included only when compilation was requested and succeeded.

Ground replacement IDs are base-game sprite IDs, NOT arbitrary NewGRF-local IDs.
Check the target climate and slopes in OpenTTD before using a replacement set.
Ground models use their TTD slope silhouette, or a reference/flat footprint in custom mode.
Raised tile objects and buildings are restricted to flat land. Buildings export
separate tile/view/stage sprites with tile-local offsets and per-tile sorting boxes.
Town houses include population, PASS/MAIL and four generated construction stages.
Each house orientation is a separate growth variation.

Compilation does not certify in-game placement, lighting or sprite sorting.
The source references and their licensing remain the responsibility of the author.
""",encoding="utf-8")
    out=io.BytesIO()
    with zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(directory.rglob("*")):
            if file.is_file() and file.suffix in (".png",".json",".nml",".nfo",".lng",".grf",".txt"):
                archive.write(file,file.relative_to(directory).as_posix())
    return out.getvalue(),manifest,directory
