# SPDX-License-Identifier: GPL-2.0-only
"""Versioned project state. A heightfield is a grid of solid voxel columns."""
import math
import re
from .geometry import SHAPES, SLOPE_NAMES, SLOPE_OFFSETS, apply_ttd_slope


def number(value, low, high, name):
    value = float(value)
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}")
    return value


def default_project():
    return {"version": 1, "name": "Meadow", "size": 16, "heights": [0]*256,
            "colours": ["#648b39"]*256, "tags": [0]*256,
            "shapes": ["cube"]*256, "rotations": [0]*256, "rises": [.5]*256,
            "terrain_slope": None, "terrain_base": 3981,
            "building": None,
            "palette": "dos", "colour_mode": "both", "dither": False,
            "palette_mapping": "nearest",
            "profile": "ground", "zoom": 1, "export_zooms": [1, 2, 4],
            "texture": "none", "texture_light": 0, "reference": None,
            "light": {"azimuth": 55, "elevation": 60, "ambient": .55, "strength": .55,
                      "shadows": .3, "ao": .12},
            "replacement_id": 3981, "variants": False}


def validate(data):
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("Unsupported project version")
    p = default_project()
    p.update(data)
    n = p["size"]
    if type(n) is not int or n not in (8, 16, 32):
        raise ValueError("Grid size must be 8, 16 or 32")
    for field,value in (("shapes","cube"),("rotations",0),("rises",8/n)):
        if field not in data:
            p[field]=[value]*(n*n)
    for field in ("heights", "colours", "tags", "shapes", "rotations", "rises"):
        if not isinstance(p[field], list) or len(p[field]) != n*n:
            raise ValueError(f"{field} must contain {n*n} cells")
    p["heights"] = [number(v, 0, 64, "Height") for v in p["heights"]]
    p["rises"] = [number(v, 0, 64, "Shape rise") for v in p["rises"]]
    if any(not isinstance(s,str) or s not in SHAPES for s in p["shapes"]):
        raise ValueError("Unsupported voxel shape")
    if any(type(r) is not int or not 0<=r<=3 for r in p["rotations"]):
        raise ValueError("Shape rotation must be 0..3")
    if any(h+r>64 for h,r,s in zip(p["heights"],p["rises"],p["shapes"]) if s!="cube"):
        raise ValueError("Shape top must not exceed 64 game pixels")
    if p["terrain_slope"] is not None and (type(p["terrain_slope"]) is not int or p["terrain_slope"] not in SLOPE_NAMES):
        raise ValueError("Unsupported TTD terrain slope")
    if type(p["terrain_base"]) is not int or not 0<=p["terrain_base"]<=4877:
        raise ValueError("Terrain sprite family base must be 0..4877")
    if any(not isinstance(c, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", c) for c in p["colours"]):
        raise ValueError("Colours must be #RRGGBB")
    if any(type(t) is not int or not 0 <= t <= 255 for t in p["tags"]):
        raise ValueError("Palette tags must be indices 0..255")
    enums = {"palette": ("dos", "windows"), "palette_mapping": ("nearest","balanced"), "colour_mode": ("8bpp", "32bpp", "both"),
             "profile": ("ground", "object", "building", "house"), "texture": ("none", "project", "surface")}
    for key, choices in enums.items():
        if p[key] not in choices:
            raise ValueError(f"Invalid {key}")
    if p["building"] is not None:
        from .building import validate_building
        p["building"] = validate_building(p["building"])
    if p["profile"] in ("building", "house") and p["building"] is None:
        raise ValueError("Choose a building preset to create a building model")
    if p["zoom"] not in (1, 2, 4) or not p["export_zooms"] or any(type(z) is not int or z not in (1, 2, 4) for z in p["export_zooms"]):
        raise ValueError("Zoom must be 1, 2 or 4")
    p["export_zooms"] = sorted(set(p["export_zooms"]))
    p["light"] = {**default_project()["light"], **p["light"]}
    for key, lo, hi in [("azimuth", 0, 360), ("elevation", 5, 90), ("ambient", 0, 1),
                        ("strength", 0, 2), ("shadows", 0, 1), ("ao", 0, .6)]:
        p["light"][key] = number(p["light"][key], lo, hi, key)
    p["texture_light"] = number(p["texture_light"], 0, 1, "Texture lighting")
    if type(p["replacement_id"]) is not int or not 0 <= p["replacement_id"] <= 16383:
        raise ValueError("Replacement sprite ID must be 0..16383")
    p["name"] = str(p["name"])[:80]
    if p["reference"] is not None and not isinstance(p["reference"], dict):
        raise ValueError("Invalid reference")
    return p


def preset(project, kind):
    p = validate(project)
    if kind.startswith("building_"):
        from .building import building_preset
        return building_preset(p,kind[9:])
    n = p["size"]
    ramps={"slope_ne":12,"slope_sw":3,"slope_nw":9,"slope_se":6}
    if kind in ramps or kind.startswith("ttd_"):
        slope=ramps[kind] if kind in ramps else int(kind[4:])
        return apply_ttd_slope(p,slope)
    heights = []
    for y in range(n):
        for x in range(n):
            u, v = x/(n-1), y/(n-1)
            h = {"flat": 0, "slope_ne": 8*(1-u), "slope_sw": 8*u,
                 "slope_nw": 8*(1-v), "slope_se": 8*v,
                 "mound": max(0, 9*(1-2*math.hypot(u-.5, v-.5))),
                 "terrace": 8 if .2 < u < .8 and .2 < v < .8 else 0}.get(kind)
            if h is None:
                raise ValueError("Unknown terrain preset")
            heights.append(round(h))
    p["heights"] = heights
    p.update(shapes=["cube"]*(n*n),rotations=[0]*(n*n),rises=[8/n]*(n*n),terrain_slope=None)
    return p


def replacement_target(project):
    if project["terrain_slope"] is None:
        return project["replacement_id"]
    return project["terrain_base"]+SLOPE_OFFSETS[project["terrain_slope"]]


def resize(project,size):
    p=validate(project)
    if type(size) is not int or size not in (8,16,32):
        raise ValueError("Grid size must be 8, 16 or 32")
    old=p["size"]
    native=False
    if p["terrain_slope"] is not None:
        canonical=apply_ttd_slope(dict(p),p["terrain_slope"])
        native=all(p[key]==canonical[key] for key in ("heights","shapes","rotations","rises"))
    if not native and any(s!="cube" for s in p["shapes"]):
        raise ValueError("Change the grid before sculpting custom shapes. Unedited TTD presets resize exactly; custom caps keep their current grid.")
    for key in ("heights","colours","tags"):
        source=p[key]
        p[key]=[source[(y*old//size)*old+x*old//size] for y in range(size) for x in range(size)]
    p.update(size=size,shapes=["cube"]*(size*size),rotations=[0]*(size*size),rises=[8/size]*(size*size))
    return apply_ttd_slope(p,p["terrain_slope"]) if native else p
