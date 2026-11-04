# SPDX-License-Identifier: GPL-2.0-only
"""Build pinned GRFCodec with static PNG/zlib; retain exact corresponding sources."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import urllib.request

ROOT=Path(__file__).resolve().parent.parent
VENDORS={
    "zlib":("madler/zlib","51b7f2abdade71cd9bb0e7a373ef2610ec6f9daf","1.3.1"),
    "libpng":("pnggroup/libpng","2b978915d82377df13fcbb1fb56660195ded868a","1.6.50"),
    "grfcodec":("OpenTTD/grfcodec","4c71c0a0294024f16cde9edecd28aecf50e60b83","6.1.0-g4c71c0a"),
}


def download(url,destination,sha256=None):
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    if not destination.exists():
        with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"TTD-Voxels-release-builder"}),timeout=60) as response:
            destination.write_bytes(response.read())
    digest=hashlib.sha256(destination.read_bytes()).hexdigest()
    if sha256 and digest!=sha256:raise RuntimeError(f"Source archive hash mismatch: {destination.name}")
    return digest


def source(name,work):
    repo,revision,version=VENDORS[name]
    archive=work/"sources"/f"{name}-{version}-{revision[:12]}.tar.gz"
    url=f"https://codeload.github.com/{repo}/tar.gz/{revision}"
    digest=download(url,archive)
    directory=work/"src"/(name+"-"+revision[:12])
    if not directory.exists():
        stage=work/"src"/f"extract-{name}-{revision[:12]}";stage.mkdir(parents=True,exist_ok=True)
        with tarfile.open(archive) as tar:tar.extractall(stage,filter="data")
        children=list(stage.iterdir())
        if len(children)!=1 or not children[0].is_dir():raise RuntimeError("Unexpected source archive layout")
        children[0].rename(directory)
    return directory,{"name":name,"version":version,"revision":revision,"url":url,"sha256":digest,"archive":str(archive.resolve()),"directory":str(directory)}


def build(work=None,generator=None):
    work=Path(work or ROOT/".work/native-codec").resolve();work.mkdir(parents=True,exist_ok=True)
    prefix=work/"install";records=[];sources={}
    for name in VENDORS:
        sources[name],record=source(name,work);records.append(record)
    (sources["grfcodec"]/".version").write_text(VENDORS["grfcodec"][2]+"\t2026-11-04\n",encoding="utf-8")
    common=[f"-DCMAKE_INSTALL_PREFIX={prefix}","-DCMAKE_BUILD_TYPE=Release","-DCMAKE_POSITION_INDEPENDENT_CODE=ON",
            "-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded","-DCMAKE_POLICY_DEFAULT_CMP0091=NEW",
            "-DCMAKE_POLICY_VERSION_MINIMUM=3.5","-DZLIB_USE_STATIC_LIBS=ON",
            "-DBUILD_SHARED_LIBS=OFF",f"-DCMAKE_PREFIX_PATH={prefix}"]
    def cmake(name,options,targets):
        directory=work/"build"/(name+"-"+VENDORS[name][1][:12])
        command=["cmake","-S",str(sources[name]),"-B",str(directory),*common,*options]
        if generator:command.extend(["-G",generator])
        subprocess.run(command,check=True)
        subprocess.run(["cmake","--build",str(directory),"--config","Release","--parallel","2","--target",*targets],check=True)
    # Build only the static target: zlib's shared Windows resource compiler
    # mishandles source directories containing spaces with some MinGW releases.
    cmake("zlib",["-DZLIB_BUILD_EXAMPLES=OFF"],["zlibstatic"])
    import shutil
    (prefix/"include").mkdir(parents=True,exist_ok=True);(prefix/"lib").mkdir(parents=True,exist_ok=True)
    zbuild=work/"build"/("zlib-"+VENDORS["zlib"][1][:12])
    for header in (sources["zlib"]/"zlib.h",zbuild/"zconf.h"):
        shutil.copyfile(header,prefix/"include"/header.name)
    libraries=list(zbuild.rglob("*.a"))+list(zbuild.rglob("*.lib"))
    zlib=next((p for p in libraries if "zlibstatic" in p.name.lower() or p.name in ("libz.a","z.lib")),None)
    if zlib is None:raise RuntimeError("Static zlib library not found")
    shutil.copyfile(zlib,prefix/"lib"/zlib.name);zlib=prefix/"lib"/zlib.name
    z_options=[f"-DZLIB_LIBRARY={zlib}",f"-DZLIB_LIBRARY_RELEASE={zlib}",f"-DZLIB_INCLUDE_DIR={prefix/'include'}"]
    cmake("libpng",["-DPNG_SHARED=OFF","-DPNG_STATIC=ON","-DPNG_TESTS=OFF","-DPNG_TOOLS=OFF","-DPNG_EXECUTABLES=OFF",*z_options],["install"])
    libraries=list((prefix/"lib").glob("*.a"))+list((prefix/"lib").glob("*.lib"))+list((prefix/"lib64").glob("*.a"))
    png=next((p for p in libraries if "png" in p.name.lower() and not p.name.endswith(".dll.a")),None)
    if png is None:raise RuntimeError("Static libpng library not found")
    cmake("grfcodec",[f"-DPNG_LIBRARY={png}",f"-DPNG_LIBRARY_RELEASE={png}",f"-DPNG_PNG_INCLUDE_DIR={prefix/'include'}",*z_options],["grfcodec"])
    cbuild=work/"build"/("grfcodec-"+VENDORS["grfcodec"][1][:12])
    candidates=[cbuild/"Release/grfcodec.exe",cbuild/"grfcodec.exe",cbuild/"grfcodec"]
    binary=next((p for p in candidates if p.is_file()),None)
    if binary is None:raise RuntimeError("GRFCodec build produced no executable")
    result=subprocess.run([str(binary),"-v"],capture_output=True,text=True)
    if "6.1.0" not in result.stdout+result.stderr:
        raise RuntimeError("GRFCodec does not report the pinned release version")
    report={"binary":str(binary),"sources":records}
    (work/"manifest.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    return binary,records


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--generator");args=parser.parse_args()
    binary,_=build(generator=args.generator);print(binary)
