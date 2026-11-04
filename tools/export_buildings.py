# SPDX-License-Identifier: GPL-2.0-only
"""Export original building examples as objects and growing town houses."""
import argparse
import copy
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from PIL import Image, ImageDraw, ImageFont
from voxelterrain.model import default_project,preset
from voxelterrain.render import render
from voxelterrain.palette import display_masked_rgba
from voxelterrain.export import export_bundle
from voxelterrain.server import resolve_reference


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build",action="store_true")
    parser.add_argument("--output",type=Path,default=Path("exports/buildings.zip"))
    args=parser.parse_args()
    projects=[];models=[]
    for kind in ("cottage","townhouse","office","warehouse"):
        p=preset(default_project(),"building_"+kind)
        models.append(p)
        projects.append(p)
        q=copy.deepcopy(p);q["profile"]="house";q["name"]+=" (town growth)";projects.append(q)
    raw,manifest,directory=export_bundle(projects,resolve_reference,args.build)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_bytes(raw)
    board=Image.new("RGB",(1600,1240),"#161d20");draw=ImageDraw.Draw(board)
    def font(size):
        for path in ("segoeui.ttf","DejaVuSans.ttf"):
            try:return ImageFont.truetype(path,size)
            except OSError:pass
        return ImageFont.load_default(size=size)
    draw.text((28,18),"VOXEL WORKSHOP  /  BUILDINGS",font=font(26),fill="#e0e9d2")
    draw.text((28,57),"Editable parts · four orientations · separate tile sprites · objects and town growth",font=font(17),fill="#9cac9e")
    for row,p in enumerate(models):
        for view in range(4):
            q=copy.deepcopy(p);q["building"]["view"]=view;r=render(q,zoom=4)
            image=display_masked_rgba(r.rgb,r.mask,q["palette"])
            image.thumbnail((350,205),Image.Resampling.NEAREST)
            x=12+view*397;y=100+row*280
            draw.rounded_rectangle((x,y,x+382,y+266),radius=8,fill="#242e2e",outline="#3e4c41")
            board.paste(image,(x+(382-image.width)//2,y+10+(205-image.height)//2),image)
            draw.text((x+18,y+222),f'{p["name"]}  /  {view*90}°',font=font(17),fill="#e3ecd5")
            draw.text((x+18,y+246),f'{r.bounds["xextent"]//16} × {r.bounds["yextent"]//16} tiles · {r.bounds["zextent"]} px high',font=font(13),fill="#a3b19a")
    path=args.output.with_name("building-showcase.png");board.save(path)
    print(f"{args.output.resolve()}: {len(manifest['sprites'])} separate sprite PNGs, 4 objects and 16 house orientations")
    print(f"Review image: {path.resolve()}")
    print(f"Source: {directory}")
    print(f"GRF SHA256: {manifest.get('grf_sha256','not compiled')}")


if __name__=="__main__":main()
