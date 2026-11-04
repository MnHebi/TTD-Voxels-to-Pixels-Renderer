# SPDX-License-Identifier: GPL-2.0-only
"""Export the full standard TTD terrain family and a review image."""
import argparse
import io
from pathlib import Path
import sys
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from PIL import Image,ImageDraw,ImageFont
from voxelterrain.model import default_project,preset
from voxelterrain.geometry import SLOPE_NAMES,SLOPE_OFFSETS
from voxelterrain.export import export_bundle
from voxelterrain.server import resolve_reference
from voxelterrain.render import render


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=Path("exports/ttd-slopes.zip"))
    parser.add_argument("--build",action="store_true")
    parser.add_argument("--legacy",action="store_true")
    parser.add_argument("--base",type=int,default=3981)
    args=parser.parse_args()
    projects=[]
    for slope in sorted(SLOPE_NAMES,key=SLOPE_OFFSETS.get):
        p=preset(default_project(),"ttd_"+str(slope))
        p.update(name=SLOPE_NAMES[slope],terrain_base=args.base)
        greens=["#648b39","#729943","#608535","#789c47","#6c913d"]
        p["colours"]=[greens[((j*13)^((j//16)*7))%len(greens)] for j in range(256)]
        projects.append(p)
    raw,manifest,directory=export_bundle(projects,resolve_reference,args.build,args.legacy)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_bytes(raw)
    # This image is an optional review board; the sprite export remains separate PNGs.
    board=Image.new("RGB",(1500,1100),"#161d20")
    draw=ImageDraw.Draw(board)
    def font_at(size):
        for filename in ("segoeui.ttf","DejaVuSans.ttf"):
            try:return ImageFont.truetype(filename,size)
            except OSError:pass
        return ImageFont.load_default(size=size)
    font=font_at(18)
    small=font_at(13)
    draw.text((28,20),"VOXEL TERRAIN  /  TTD SLOPE FAMILY",font=font,fill="#d9e8c9")
    draw.text((28,52),"19 continuous terrain shapes · self-authored materials · in-game art review pending",font=small,fill="#95a49b")
    for i,p in enumerate(projects):
        r=render(p,zoom=4)
        x=(i%5)*300;y=90+(i//5)*250
        draw.rounded_rectangle((x+10,y+5,x+289,y+238),radius=8,fill="#20292b",outline="#364237")
        image=r.rgb
        board.paste(image,(x+(300-image.width)//2,y+28+(160-image.height)//2),image)
        draw.text((x+24,y+190),p["name"],font=font,fill="#e5ecd9")
        draw.text((x+24,y+219),f'Slope {p["terrain_slope"]} · base sprite {args.base+SLOPE_OFFSETS[p["terrain_slope"]]}',font=small,fill="#a2b191")
    board_path=args.output.with_name("ttd-slope-showcase.png")
    board.save(board_path)
    print(f"{args.output.resolve()}: {len(manifest['sprites'])} individual sprite images")
    print(f"Review image: {board_path.resolve()}")
    print(f"Unpacked source: {directory}")


if __name__=="__main__":main()
