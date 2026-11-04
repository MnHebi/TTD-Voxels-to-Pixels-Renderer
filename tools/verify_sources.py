# SPDX-License-Identifier: GPL-2.0-only
"""Read-only checks against user-supplied GRFs; never bundle source artwork."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from voxelterrain.grf import import_grf
from voxelterrain.model import default_project
from voxelterrain.render import Reference,render

parser=argparse.ArgumentParser()
parser.add_argument("source",type=Path,nargs="+")
parser.add_argument("--palette",choices=("dos","windows"),default="dos")
parser.add_argument("--sprite",type=int,default=3981)
parser.add_argument("--report",type=Path,default=Path(".work/source-validation.json"))
args=parser.parse_args()
report=[]
for source in args.source:
    lib=import_grf(source.read_bytes(),source.name,args.palette)
    matches=[s for s in lib.sprites if s.number==args.sprite and s.zoom=="normal" and s.depth=="8bpp"]
    if not matches:raise SystemExit(f"Sprite {args.sprite} not found in {source.name}")
    s=matches[0];image,mask=lib.crop(s.key)
    ref=Reference(image,mask,s.xoffset,s.yoffset)
    p=default_project();p["palette"]=args.palette;p["texture"]="project";p["texture_light"]=0
    r=render(p,ref)
    source_rgba=np.asarray(image);output=np.asarray(r.rgb)
    equal_bounds=(r.offset== (s.xoffset,s.yoffset) and r.rgb.size==image.size)
    alpha_diff=int(np.count_nonzero(output[:,:,3]!=source_rgba[:,:,3])) if equal_bounds else -1
    rgb_diff=int(np.count_nonzero(np.any(output[:,:,:3]!=source_rgba[:,:,:3],axis=2)&(source_rgba[:,:,3]>0))) if equal_bounds else -1
    item={"file":source.name,"source_sha256":lib.digest,"container":2 if source.read_bytes()[:2]==b"\0\0" else 1,
          "variants":len(lib.sprites),"sprite":args.sprite,"bounds_equal":equal_bounds,
          "alpha_mismatches":alpha_diff,"opaque_rgb_mismatches":rgb_diff,"uncovered":r.uncovered}
    report.append(item)
    print(json.dumps(item))
    if not equal_bounds or alpha_diff or rgb_diff:raise SystemExit("Reference projection comparison failed")
args.report.parent.mkdir(parents=True,exist_ok=True)
args.report.write_text(json.dumps(report,indent=2))
