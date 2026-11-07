# SPDX-License-Identifier: GPL-2.0-only
"""GRFCodec adapter: established decoding, individually addressable sprites."""
from dataclasses import dataclass, asdict
from functools import lru_cache
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import uuid
import zipfile

from PIL import Image
from .runtime import RESOURCE_ROOT, DATA_ROOT, CONFIG_PATH, run_tool

ROOT = RESOURCE_ROOT
WORK = DATA_ROOT
MAX_UPLOAD = 128 * 1024 * 1024
MAX_SPRITE_PIXELS = 16_777_216
# GRFCodec does not quote paths containing spaces. Anchor the parser on depth.
REAL = re.compile(r'^\s*(\d+|\|)\s+(.+?)\s+(8bpp|32bpp)\s+(-?\d+)\s+(-?\d+)\s+(\d+)\s+(\d+)\s+(-?\d+)\s+(-?\d+)\s+(normal|zi2|zi4|zo2|zo4|zo8)(?:\s+(.*))?$')
MASK = re.compile(r'^\s*\|\s+(.+?)\s+mask\s+(\d+)\s+(\d+)\s*$')


def codec_path():
    configured = os.environ.get("GRFCODEC")
    config = CONFIG_PATH
    if not configured and config.exists():
        configured = json.loads(config.read_text()).get("grfcodec")
    candidates = [configured, shutil.which("grfcodec"), ROOT/"tools/grfcodec.exe", ROOT/"tools/grfcodec"]
    for path in candidates:
        if path and Path(path).is_file():
            return str(Path(path).resolve())
    raise ValueError("GRFCodec was not found. Set GRFCODEC or configure its path in local.json. See README.md.")


@dataclass
class Sprite:
    key: int
    number: int
    image: str
    depth: str
    x: int
    y: int
    width: int
    height: int
    xoffset: int
    yoffset: int
    zoom: str
    flags: str = ""
    mask_image: str | None = None
    mask_x: int = 0
    mask_y: int = 0

    def public(self):
        d = asdict(self)
        d.pop("image")
        d.pop("mask_image")
        d["has_mask"] = self.mask_image is not None
        return d


def parse_nfo(text, directory):
    sprites = []
    number = None
    for line in text.splitlines():
        m = REAL.match(line)
        if m:
            num, image, depth, x, y, w, h, dx, dy, zoom, flags = m.groups()
            if num != "|":
                number = int(num)
            if number is None:
                raise ValueError("NFO alternative has no parent sprite")
            image = directory / Path(image.replace("\\", "/")).name
            w, h = int(w), int(h)
            if w < 1 or h < 1 or w*h > MAX_SPRITE_PIXELS:
                raise ValueError("Sprite dimensions exceed the import limit")
            sprites.append(Sprite(len(sprites), number, str(image), depth, int(x), int(y),
                                  w, h, int(dx), int(dy), zoom, flags or ""))
        elif (m := MASK.match(line)):
            if not sprites or sprites[-1].depth != "32bpp":
                raise ValueError("NFO mask has no RGB sprite")
            name, x, y = m.groups()
            sprites[-1].mask_image = str(directory / Path(name.replace("\\", "/")).name)
            sprites[-1].mask_x, sprites[-1].mask_y = int(x), int(y)
    return sprites


PSEUDO = re.compile(r'^\s*\d+\s+\*\s+(\d+)\s(.*)$')
TOKEN = re.compile(r'"([^"]*)"|(\S+)')
PALS_VALUES = {b"D": "dos", b"W": "windows", b"A": "any"}


def _pseudo_bytes(tokens, data, length):
    """Append GRFCodec quoted strings and hex bytes; None for an unsupported escape."""
    for m in tokens:
        if m.group(1) is not None:
            data += m.group(1).encode("latin1")
        elif re.fullmatch(r"[0-9A-Fa-f]{2}", m.group(2)):
            data.append(int(m.group(2), 16))
        else:
            return None
        if len(data) >= length:
            break
    return data


def _info_palette(data):
    """Walk an Action 14 chunk tree and return the INFO/PALS value, if present."""
    def walk(pos, path):
        while pos < len(data):
            kind = data[pos]; pos += 1
            if kind == 0:
                return pos, None
            ident = bytes(data[pos:pos+4]); pos += 4
            if len(ident) < 4:
                raise ValueError
            if kind == ord("C"):
                pos, found = walk(pos, path+(ident,))
                if found:
                    return pos, found
            elif kind == ord("B"):
                size = int.from_bytes(data[pos:pos+2], "little"); pos += 2
                value = bytes(data[pos:pos+size]); pos += size
                if path == (b"INFO",) and ident == b"PALS" and len(value) >= 1:
                    return pos, PALS_VALUES.get(value[:1])
            elif kind == ord("T"):
                pos = data.index(0, pos+1)+1
            else:
                raise ValueError
        return pos, None
    if not data or data[0] != 0x14:
        return None
    try:
        return walk(1, ())[1]
    except (ValueError, IndexError):
        return None


def declared_palette(text):
    """Palette declared by a decoded GRF's Action 14 INFO/PALS: dos, windows, any or None."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = PSEUDO.match(line)
        if not m or not m.group(2).lstrip().startswith("14"):
            continue
        length = int(m.group(1))
        data = bytearray()
        # Pseudo-sprites may continue on following lines; the declared length delimits them.
        for part in [m.group(2), *lines[i+1:i+64]]:
            data = _pseudo_bytes(TOKEN.finditer(part), data, length)
            if data is None or len(data) >= length:
                break
        if data is not None and len(data) == length and (found := _info_palette(data)):
            return found
    return None


class Library:
    def __init__(self, name, directory, sprites, palette, digest, declared=None):
        self.id = uuid.uuid4().hex
        self.name, self.directory, self.sprites, self.palette, self.digest = name, directory, sprites, palette, digest
        self.declared = declared
        self.lock = threading.RLock()

    @lru_cache(maxsize=6)
    def sheet(self, filename):
        im = Image.open(filename)
        im.load()
        return im

    def get(self, key):
        if type(key) is not int or not 0 <= key < len(self.sprites):
            raise ValueError("Unknown sprite")
        return self.sprites[key]

    def crop(self, key):
        s = self.get(key)
        with self.lock:
            image = self.sheet(s.image).crop((s.x, s.y, s.x+s.width, s.y+s.height))
            if image.mode == "P":
                image.info["transparency"] = 0
            mask = None
            if s.mask_image:
                mask = self.sheet(s.mask_image).crop((s.mask_x, s.mask_y, s.mask_x+s.width, s.mask_y+s.height))
            elif image.mode == "P":
                mask = image.copy()
            return image.convert("RGBA"), mask


def _decode(codec, source, output, palette, directory):
    if output.exists():
        shutil.rmtree(output)
    result = run_tool([codec, "-s", "-d", "-o", "png", "-p", "1" if palette == "dos" else "2",
                             str(source), str(output)], cwd=directory, capture_output=True, timeout=120,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode:
        message = (result.stderr+result.stdout).decode("utf-8", errors="replace")[-1200:]
        raise ValueError(f"GRFCodec could not decode this file: {message}")
    text = (output / "source.nfo").read_text(encoding="latin1")
    return parse_nfo(text, output), declared_palette(text)


def import_grf(payload, name, palette="auto"):
    """Decode a GRF. "auto" uses the GRF's declared palette, falling back to DOS."""
    if palette not in ("auto", "dos", "windows"):
        raise ValueError("Select Auto, DOS or Windows palette")
    if not payload or len(payload) > MAX_UPLOAD:
        raise ValueError("GRF files must be between 1 byte and 128 MiB")
    codec = codec_path()
    directory = WORK / "imports" / uuid.uuid4().hex
    directory.mkdir(parents=True)
    source = directory / "source.grf"
    source.write_bytes(payload)
    output = directory / "sprites"
    try:
        used = "dos" if palette == "auto" else palette
        sprites, declared = _decode(codec, source, output, used, directory)
        if palette == "auto" and declared == "windows":
            used = "windows"
            # Only indexed sprites depend on the decoding palette.
            if any(s.depth == "8bpp" for s in sprites):
                sprites, declared = _decode(codec, source, output, used, directory)
        if not sprites:
            raise ValueError("This GRF contains no image sprites")
        return Library(Path(name.replace("\\", "/")).name, directory, sprites, used, hashlib.sha256(payload).hexdigest(), declared)
    except Exception:
        # This exact generated directory is owned by this import, never an input path.
        target=directory.resolve()
        owned_root=(WORK/"imports").resolve()
        if target.parent==owned_root and target.is_relative_to(WORK.resolve()):
            shutil.rmtree(target)
        raise


def export_references(library, key=None):
    """Separate original images plus exact metadata, without an intermediate atlas."""
    selected=library.sprites if key is None else [library.get(key)]
    manifest={"schema":1,"source":library.name,"source_sha256":library.digest,
              "palette":library.palette,"sprites":[]}
    out=io.BytesIO()
    total=0
    with zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED) as archive:
        for s in selected:
            image,mask=library.crop(s.key)
            if s.depth=="8bpp":
                image=mask
            file=f"sprites/{s.key:06d}_sprite{s.number}_{s.zoom}_{s.depth}.png"
            png=io.BytesIO();image.save(png,format="PNG")
            raw=png.getvalue();total+=len(raw)
            if total>256*1024*1024:
                raise ValueError("Reference export exceeds 256 MiB. Export individual selections instead.")
            archive.writestr(file,raw)
            record=s.public()
            record.update(file=file,sha256=hashlib.sha256(raw).hexdigest())
            if s.depth=="32bpp" and mask is not None:
                maskfile=file.replace("_32bpp.png","_mask.png")
                png=io.BytesIO();mask.save(png,format="PNG")
                archive.writestr(maskfile,png.getvalue());record["mask"]=maskfile
            manifest["sprites"].append(record)
        archive.writestr("manifest.json",json.dumps(manifest,indent=2))
    return out.getvalue()
