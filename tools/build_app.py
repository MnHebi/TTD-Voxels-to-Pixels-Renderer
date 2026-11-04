# SPDX-License-Identifier: GPL-2.0-only
"""Build a native, browser-based standalone app, its source and licence notices."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from voxelterrain import __version__
from build_grfcodec import build as build_codec, download

APP="TTDVoxelsToPixels"


def application_source(destination):
    roots=["voxelterrain","web","tools","tests","assets","docs",".github"]
    files=[ROOT/name for name in ("app.py","README.md","LICENSE","LICENSE_NOTICE.md","THIRD_PARTY.md","VALIDATION.md",
                                "requirements.txt","requirements-build.txt","Start Workshop.cmd",".gitignore",".gitattributes")]
    for name in roots:
        folder=ROOT/name
        if folder.exists():files.extend(p for p in folder.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix!=".pyc")
    with zipfile.ZipFile(destination,"w",zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(files):
            if file.is_file():archive.write(file,file.relative_to(ROOT))


def dependency_licenses(destination):
    destination.mkdir(parents=True,exist_ok=True)
    inventory={}
    for name in ("Pillow","numpy","nml","ply","pyinstaller","pyinstaller-hooks-contrib","altgraph","packaging","pefile","pywin32-ctypes"):
        try:dist=importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError:continue
        inventory[name]=dist.version
        for file in dist.files or []:
            if any(word in file.name.lower() for word in ("license","licence","copying","copyright","notice")) and dist.locate_file(file).is_file():
                source=Path(dist.locate_file(file));target=destination/name/str(file).replace("../","")
                target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    candidates=[Path(sys.base_prefix)/"LICENSE.txt",Path(sys.base_prefix)/"LICENSE",Path(sys.executable).parent/"LICENSE.txt"]
    license=next((p for p in candidates if p.is_file()),None)
    if license:shutil.copyfile(license,destination/"Python-LICENSE.txt")
    else:download(f"https://raw.githubusercontent.com/python/cpython/v{platform.python_version()}/LICENSE",destination/"Python-LICENSE.txt")
    (destination/"DEPENDENCIES.json").write_text(json.dumps({"python":platform.python_version(),**inventory},indent=2)+"\n",encoding="utf-8")
    return inventory


def nml_source(destination):
    version=importlib.metadata.version("nml")
    with urllib.request.urlopen(f"https://pypi.org/pypi/nml/{version}/json",timeout=60) as response:metadata=json.load(response)
    source=next(item for item in metadata["urls"] if item["packagetype"]=="sdist")
    target=destination/source["filename"]
    digest=download(source["url"],target,source["digests"]["sha256"])
    return {"name":"nml","version":version,"url":source["url"],"sha256":digest,"archive":target.name}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generator",help="CMake generator for GRFCodec, e.g. Ninja")
    parser.add_argument("--without-grfcodec",action="store_true",help="Build the editor/compiler only (not a full release)")
    parser.add_argument("--output",type=Path,default=ROOT/"dist")
    args=parser.parse_args()
    if sys.version_info<(3,12):parser.error("Release builds require Python 3.12+")
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    system={"win32":"windows","linux":"linux","darwin":"macos"}.get(sys.platform,sys.platform)
    arch={"amd64":"x64","x86_64":"x64","aarch64":"arm64"}.get(platform.machine().lower(),platform.machine().lower())
    label=f"{system}-{arch}";work=ROOT/".work/packages"/label;work.mkdir(parents=True,exist_ok=True)
    sources=[];codec=None
    if not args.without_grfcodec:codec,sources=build_codec(generator=args.generator)
    command=[sys.executable,"-m","PyInstaller","--noconfirm","--onedir","--console","--noupx","--name",APP,
             "--distpath",str(work/"dist"),"--workpath",str(work/"build"),"--specpath",str(work),
             "--add-data",f"{ROOT/'web'}:web","--add-data",f"{ROOT/'assets'}:assets",
             "--collect-all","nml","--copy-metadata","nml"]
    if codec:command.extend(["--add-binary",f"{codec}:tools"])
    command.append(str(ROOT/"app.py"));subprocess.run(command,cwd=ROOT,check=True)
    bundle=work/"dist"/APP
    for name in ("README.md","LICENSE","LICENSE_NOTICE.md","THIRD_PARTY.md"):
        shutil.copyfile(ROOT/name,bundle/name)
    source_dir=bundle/"sources";source_dir.mkdir(exist_ok=True)
    application_source(source_dir/f"TTDVoxelsToPixels-{__version__}-source.zip")
    source_records=[]
    for record in sources:
        archive=Path(record["archive"]);shutil.copyfile(archive,source_dir/archive.name)
        source_records.append({k:v for k,v in {**record,"archive":archive.name}.items() if k!="directory"})
    source_records.append(nml_source(source_dir))
    inventory=dependency_licenses(bundle/"licenses")
    # Include native helper notices in addition to its exact source archives.
    if codec:
        for name,filename in (("grfcodec","COPYING"),("zlib","LICENSE"),("libpng","LICENSE")):
            source=Path(next(r["directory"] for r in sources if r["name"]==name))/filename
            if not source.exists() and name=="libpng":source=source.with_name("LICENSE.md")
            if not source.is_file():raise RuntimeError(f"Missing native dependency licence: {source}")
            shutil.copyfile(source,bundle/"licenses"/f"{name}-LICENSE.txt")
    if system=="windows":
        (bundle/"Start Workshop.cmd").write_text('@echo off\r\n"%~dp0TTDVoxelsToPixels.exe" %*\r\nif errorlevel 1 pause\r\n',encoding="utf-8")
    else:
        launcher=bundle/("Start Workshop.command" if system=="macos" else "start-workshop.sh")
        launcher.write_text('#!/bin/sh\ncd "$(dirname "$0")" || exit 1\nexec ./TTDVoxelsToPixels "$@"\n',encoding="utf-8");launcher.chmod(0o755)
    manifest={"application":APP,"version":__version__,"platform":label,"python":platform.python_version(),
              "dependencies":inventory,"grfcodec_bundled":codec is not None,
              "validation":"BUILD_ONLY_RUN_SMOKE_TEST","manual_macos_validation":"PENDING_COMMUNITY_REVIEW" if system=="macos" else None,
              "sources":source_records}
    (bundle/"BUNDLE_MANIFEST.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    (bundle/"START_HERE.txt").write_text(f'''TTD Voxels to Pixels Renderer {__version__} ({label})

Extract the COMPLETE folder before launching. No Python installation is needed.
Run TTDVoxelsToPixels{'.exe' if system=='windows' else ''} or the included launcher.
The app starts a local server and opens your normal web browser.
Keep its terminal open; Ctrl+C stops the backend. Closing the browser does not stop it.

Includes Python, Pillow, NumPy, NML{' and GRFCodec' if codec else ''}.
Data is stored in your OS user-data folder, separate from this application folder.
Use --data-dir PATH to choose another location, or --port 7866 if port 7865 is busy.
Browser autosave is per profile and local URL. Save project files for backups.

macOS builds are unsigned and have NOT received hands-on Mac validation.
They require community testing; automated smoke tests are not visual acceptance.
See README.md, LICENSE, licenses/ and sources/ for usage, notices and source code.
''',encoding="utf-8")
    filename=f"TTDVoxelsToPixels-{__version__}-{label}"
    if system=="windows":
        archive=Path(shutil.make_archive(str(output/filename),"zip",bundle.parent,bundle.name))
    else:
        archive=output/(filename+".tar.gz")
        with tarfile.open(archive,"w:gz",dereference=False) as tar:tar.add(bundle,arcname=bundle.name)
    (output/(archive.name+".sha256")).write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+"  "+archive.name+"\n",encoding="utf-8")
    print(json.dumps({"archive":str(archive),"bundle":str(bundle),"platform":label},indent=2))


if __name__=="__main__":main()
