# SPDX-License-Identifier: GPL-2.0-only
"""Per-tile building graphics, NewObjects and growing town houses."""
import copy
import hashlib
import math

import numpy as np

from .building import footprint
from .render import render, building_fragments

ZOOMS={1:"ZOOM_LEVEL_NORMAL",2:"ZOOM_LEVEL_IN_2X",4:"ZOOM_LEVEL_IN_4X"}


def export_building(p, ref, directory, index, stem, manifest, nml, lang, entry):
    b=p["building"];house=p["profile"]=="house"
    views=range(4) if b["views"]==4 else [b["view"]]
    stages=range(4) if house else [3]
    zooms=sorted({1,*p["export_zooms"]})
    graphics={};bounds={};purchase={}

    def save(r,key,view,stage,x,y,zoom,mode,role):
        file=f"sprites/{stem}_{key}_{zoom}x_{mode}.png"
        image=r.palette_image if mode=="8bpp" else r.rgb
        image.save(directory/file,transparency=0 if mode=="8bpp" else None)
        rec={"tile":index,"name":p["name"],"file":file,"mode":mode,"zoom":zoom,
             "width":image.width,"height":image.height,"xoffset":r.offset[0],"yoffset":r.offset[1],
             "view":view,"stage":stage,"tile_x":x,"tile_y":y,"role":role,"sorting_bounds":r.bounds,
             "sha256":hashlib.sha256((directory/file).read_bytes()).hexdigest(),
             "fallback":mode=="8bpp" and p["colour_mode"]=="32bpp",
             "untextured_pixels":r.uncovered,"clipped_pixels":0,"missing_ground_pixels":0}
        if mode=="32bpp" and np.any(np.asarray(r.mask)):
            file=f"sprites/{stem}_{key}_{zoom}x_mask.png";r.mask.save(directory/file,transparency=0)
            rec.update(mask=file,mask_sha256=hashlib.sha256((directory/file).read_bytes()).hexdigest())
        manifest["sprites"].append(rec)
        return rec

    for view in views:
        q=copy.deepcopy(p);q["building"]["view"]=view
        for stage in stages:
            q["building"]["stage"]=stage
            for zoom in zooms:
                result=render(q,ref,zoom)
                modes=["8bpp"] if p["colour_mode"]=="8bpp" else ["8bpp","32bpp"] if p["colour_mode"]=="both" or zoom==1 else ["32bpp"]
                for x,y,r in building_fragments(result,q["building"],zoom):
                    bounds[view,x,y]=r.bounds
                    key=f"v{view}_x{x}_y{y}_s{stage}"
                    for mode in modes:graphics[view,x,y,stage,zoom,mode]=save(r,key,view,stage,x,y,zoom,mode,"tile")
                if not house:
                    for mode in modes:purchase[view,zoom,mode]=save(result,f"v{view}_purchase",view,stage,None,None,zoom,mode,"purchase")

    def sprites(block, records):
        nml.append(f'spriteset({block}) {{ '+" ".join(entry(r) for r in records[1,"8bpp"])+" }")
        for (zoom,mode),rows in records.items():
            if (zoom,mode)==(1,"8bpp"):continue
            nml.append(f'alternative_sprites({block}, {ZOOMS[zoom]}, BIT_DEPTH_{mode.upper()}) {{ '+" ".join(entry(r,mode=="32bpp") for r in rows)+" }")

    safe_name=p["name"].replace("\n"," ").replace("\r"," ").replace("{","(").replace("}",")")
    lang.append(f"STR_BUILDING_{index} :{safe_name}")
    view_switch=[];purchase_switch=[]
    for ordinal,view in enumerate(views):
        w,d=footprint(b,view);cases=[]
        for y in range(d):
            for x in range(w):
                block=f"b{index}_v{view}_{x}_{y}"
                records={}
                for zoom in zooms:
                    for mode in ("8bpp","32bpp"):
                        rows=[graphics[view,x,y,stage,zoom,mode] for stage in stages if (view,x,y,stage,zoom,mode) in graphics]
                        if rows:records[zoom,mode]=rows
                sprites(block,records)
                z=bounds[view,x,y]["zextent"]
                nml.append(f'''spritelayout {block}_layout {{
    ground {{ sprite: GROUNDSPRITE_NORMAL; }}
    building {{ sprite: {block}; xextent: 16; yextent: 16; zextent: {z}; recolour_mode: RECOLOUR_REMAP; palette: PALETTE_USE_DEFAULT; }}
}}''')
                cases.append(f"relative_coord({x},{y}): {block}_layout;")
        feature="FEAT_HOUSES" if house else "FEAT_OBJECTS"
        route=f"b{index}_v{view}_tiles"
        nml.append(f'switch({feature}, SELF, {route}, relative_pos) {{ '+" ".join(cases)+f" b{index}_v{view}_0_0_layout; }}")
        if house:
            substitute={(1,1):0,(1,2):7,(2,1):74,(2,2):20}[w,d]
            nml.append(f'''item(FEAT_HOUSES, house_{index}_v{view}, -1, HOUSE_SIZE_{w}X{d}) {{
    property {{ substitute: {substitute}; name: string(STR_BUILDING_{index});
        building_flags: bitmask(HOUSE_FLAG_NOT_SLOPED);
        population: {b['population']}; mail_multiplier: {b['mail']};
        accepted_cargos: [[PASS, {b['passenger_acceptance']}], [MAIL, {b['mail_acceptance']}]];
        probability: {b['probability']}; years_available: [{b['year_from']}, {b['year_to']}];
        availability_mask: [ALL_TOWNZONES, ALL_CLIMATES | bitmask(ABOVE_SNOWLINE)];
        minimum_lifetime: 10;
    }}
    graphics {{ default: {route}; }}
}}''')
        else:
            view_switch.append(f"{ordinal}: {route};")
            block=f"b{index}_v{view}_purchase"
            sprites(block,{(z,m):[r] for (v,z,m),r in purchase.items() if v==view})
            z=bounds[view,0,0]["zextent"]
            nml.append(f'spritelayout {block}_layout {{ building {{ sprite: {block}; zextent: {z}; recolour_mode: RECOLOUR_REMAP; palette: PALETTE_USE_DEFAULT; }} }}')
            purchase_switch.append(f"{ordinal}: {block}_layout;")
    if not house:
        nml.append(f'switch(FEAT_OBJECTS, SELF, b{index}_views, view) {{ '+" ".join(view_switch)+f" b{index}_v{list(views)[0]}_tiles; }}")
        nml.append(f'switch(FEAT_OBJECTS, SELF, b{index}_purchase, view) {{ '+" ".join(purchase_switch)+f" b{index}_v{list(views)[0]}_purchase_layout; }}")
        w,d=footprint(b,list(views)[0]);z=max(v["zextent"] for v in bounds.values())
        # This callback is called before an object exists; use callback parameters.
        nml.append(f'''switch(FEAT_OBJECTS, SELF, b{index}_location, getbits(extra_callback_info1, 0, 5)) {{
    SLOPE_FLAT: return CB_RESULT_LOCATION_ALLOW;
    return CB_RESULT_LOCATION_DISALLOW;
}}
item(FEAT_OBJECTS, building_{index}) {{
    property {{ class: "VXBL"; classname: string(STR_BUILDING_CLASS); name: string(STR_BUILDING_{index});
        climates_available: ALL_CLIMATES; size: [{w},{d}]; num_views: {len(views)};
        build_cost_multiplier: 1; remove_cost_multiplier: 1;
        introduction_date: date(0,1,1); end_of_life_date: date(5000000,1,1); height: {math.ceil(z/8)}; }}
    graphics {{ default: b{index}_views; purchase: b{index}_purchase; tile_check: b{index}_location; }}
}}''')
    manifest["tiles"].append({"name":p["name"],"profile":p["profile"],"footprint":[b["width"],b["depth"]],
                              "palette_mapping":p["palette_mapping"],
                              "views":list(views),"stages":list(stages),"parts":len(b["parts"]),
                              "sorting_policy":"Per-tile 16x16 conservative box, geometry-derived height; no box crosses a tile boundary",
                              "town_properties":{k:b[k] for k in ("population","mail","passenger_acceptance","mail_acceptance","probability","year_from","year_to")} if house else None,
                              "reference":ref.provenance if ref else None})
