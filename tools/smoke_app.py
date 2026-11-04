# SPDX-License-Identifier: GPL-2.0-only
"""Exercise an extracted standalone bundle without Python or GRFCodec on its PATH."""
import argparse
import io
import json
import os
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import time
import tarfile
import urllib.request
import zipfile

from PIL import Image


def smoke(executable, report_path):
    executable=Path(executable).resolve();report_path=Path(report_path).resolve()
    with tempfile.TemporaryDirectory(prefix="ttd-voxels-smoke-") as temp:
        temp=Path(temp);data=temp/"user data";env=os.environ.copy()
        for key in ("PYTHONPATH","PYTHONHOME","GRFCODEC","TTD_VOXELS_DATA_DIR"):env.pop(key,None)
        env["PATH"]=os.pathsep.join([str(Path(os.environ.get("SystemRoot","C:/Windows"))/"System32")] if os.name=="nt" else ["/usr/bin","/bin"])
        process=subprocess.Popen([str(executable),"--no-browser","--port","0","--data-dir",str(data)],
                                 cwd=temp,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,
                                 creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        lines=[];messages=queue.Queue()
        def read():
            for line in process.stdout:lines.append(line.rstrip());messages.put(line)
        threading.Thread(target=read,daemon=True).start()
        url=None;deadline=time.monotonic()+60
        try:
            while time.monotonic()<deadline:
                try:line=messages.get(timeout=.2)
                except queue.Empty:
                    if process.poll() is not None:raise RuntimeError("Packaged app exited: "+"\n".join(lines))
                    continue
                if line.startswith("Voxel Terrain Workshop: "):url=line.split(": ",1)[1].strip();break
            if not url:raise RuntimeError("Packaged app did not become ready: "+"\n".join(lines))
            def call(path,body=None,raw=False):
                headers={}
                if body is not None:
                    headers={"X-Workshop-Token":token,"Content-Type":"application/octet-stream" if raw else "application/json"}
                    body=body if raw else json.dumps(body).encode()
                with urllib.request.urlopen(urllib.request.Request(url.rstrip("/")+path,data=body,headers=headers),timeout=120) as response:return response.read()
            boot=json.loads(call("/api/bootstrap"));token=boot["token"]
            assert boot["compiler"],"Bundled NML compiler was not found"
            assert boot["codec"],"Bundled GRFCodec was not found"
            for path in ("/","/app.js","/pictures.js","/style.css"):assert len(call(path))>100
            p=boot["project"];p["export_zooms"]=[1];p["colour_mode"]="both";p["palette_mapping"]="balanced"
            result=json.loads(call("/api/render",p));assert result["width"]==64 and result["height"]==31
            output=call("/api/export",{"projects":[p],"build":True,"legacy":False})
            with zipfile.ZipFile(io.BytesIO(output)) as bundle:
                manifest=json.loads(bundle.read("manifest.json"));grf=bundle.read("workshop.grf")
                assert manifest["compiled"] and len(manifest["sprites"])==2
            imported=json.loads(call("/api/import?name=smoke.grf&palette=dos",grf,True));assert imported["count"]>=2
            legacy=call("/api/export",{"projects":[p],"build":True,"legacy":True})
            with zipfile.ZipFile(io.BytesIO(legacy)) as bundle:assert bundle.read("workshop.grf")[:2]!=b"\0\0"
            photo=io.BytesIO();Image.new("RGB",(24,16),(96,112,88)).save(photo,format="JPEG")
            picture=json.loads(call("/api/pictures/import?name=smoke.jpg",photo.getvalue(),True))
            converted=json.loads(call("/api/pictures/convert",{"png":picture["png"],"palette":"dos","mapping":"balanced","dither":True}))
            assert converted["width"]==24 and converted["height"]==16
            assert (data/"exports").is_dir() and (data/"imports").is_dir()
            report={"status":"PASS","executable":executable.name,"python_on_child_path":False,
                    "checks":["static assets","palette load","render","bundled NML compilation","bundled GRFCodec import","legacy encoding","JPEG import","balanced palette conversion","separate writable data directory"],
                    "grf_sha256":manifest["grf_sha256"],"visual_validation":"NOT_PERFORMED"}
            report_path.parent.mkdir(parents=True,exist_ok=True);report_path.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
            print(json.dumps(report,indent=2));return report
        except Exception as exc:
            raise RuntimeError(str(exc)+"\nPACKAGED APP OUTPUT:\n"+"\n".join(lines)) from exc
        finally:
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("executable",type=Path)
    parser.add_argument("--report",type=Path,default=Path(".work/package-smoke.json"));args=parser.parse_args()
    if args.executable.name.endswith((".zip",".tar.gz")):
        with tempfile.TemporaryDirectory(prefix="ttd voxels extracted ") as folder:
            if args.executable.suffix==".zip":
                with zipfile.ZipFile(args.executable) as archive:archive.extractall(folder)
            else:
                with tarfile.open(args.executable) as archive:archive.extractall(folder,filter="data")
            binary=Path(folder)/"TTDVoxelsToPixels"/("TTDVoxelsToPixels.exe" if os.name=="nt" else "TTDVoxelsToPixels")
            smoke(binary,args.report)
    else:smoke(args.executable,args.report)
