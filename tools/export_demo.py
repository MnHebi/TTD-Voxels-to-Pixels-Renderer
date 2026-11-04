# SPDX-License-Identifier: GPL-2.0-only
"""Create a self-authored five-tile demonstration, with no external artwork."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from voxelterrain.model import default_project,preset
from voxelterrain.export import export_bundle
from voxelterrain.server import resolve_reference

parser=argparse.ArgumentParser()
parser.add_argument("--output",type=Path,default=Path("exports/demo.zip"))
parser.add_argument("--build",action="store_true")
args=parser.parse_args()
tiles=[]
for i,shape in enumerate(("flat","slope_ne","slope_nw","slope_se","slope_sw")):
    p=preset(default_project(),shape)
    p["profile"]="object"
    p["name"]="Meadow "+shape.replace("_"," ")
    greens=["#648b39","#729943","#608535","#789c47"]
    p["colours"]=[greens[((j*13)^((j//16)*7))%4] for j in range(256)]
    tiles.append(p)
raw,manifest,directory=export_bundle(tiles,resolve_reference,args.build)
args.output.parent.mkdir(parents=True,exist_ok=True)
args.output.write_bytes(raw)
print(f"{args.output.resolve()}: {len(manifest['sprites'])} individual sprites")
print(f"Unpacked files: {directory}")
