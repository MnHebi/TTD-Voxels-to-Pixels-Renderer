# SPDX-License-Identifier: GPL-2.0-only
import copy
import io
import json
import unittest
import zipfile

import numpy as np
from PIL import Image

from voxelterrain.building import BuildingGeometry, PART_SHAPES, footprint, part
from voxelterrain.export import export_bundle, compiler_available
from voxelterrain.grf import codec_path, import_grf
from voxelterrain.model import default_project, preset, validate
from voxelterrain.render import render, building_fragments, Reference
from voxelterrain.server import resolve_reference


def building(kind="cottage"):
    return preset(default_project(),"building_"+kind)


class BuildingTests(unittest.TestCase):
    def test_presets_validate_and_old_projects_remain_terrain(self):
        p=default_project();p.pop("building")
        self.assertIsNone(validate(p)["building"])
        for name in ("cottage","townhouse","office","warehouse","empty"):
            p=validate(building(name))
            self.assertEqual(p["profile"],"building")
            self.assertLessEqual(len(p["building"]["parts"]),160)
            r=render(p)
            self.assertEqual(r.missing_ground,0)
        self.assertEqual(render(building("empty")).rgb.getbbox(),None)

    def test_invalid_parts_and_gameplay_properties_are_rejected(self):
        for change in ({"x":16},{"height":129},{"height":0},{"colour":"pink"},{"rotation":4},{"tag":256},{"visible":"no"}):
            p=building();p["building"]["parts"][0].update(change)
            with self.assertRaises(ValueError):validate(p)
        for change in ({"width":3},{"views":2},{"view":4},{"stage":4},{"population":256},{"passenger_acceptance":9},{"year_to":65536},{"probability":0}):
            p=building();p["building"].update(change)
            with self.assertRaises(ValueError):validate(p)

    def test_actual_volume_keeps_space_below_raised_parts_empty(self):
        p=building();b=p["building"]
        b["parts"]=[part("Raised floor",2,3,8,10,8,2,"#cccccc")]
        probes=np.array([[5,5,1],[5,5,9],[5,5,11],[1,5,9]],dtype=float)
        for view in range(4):
            b["view"]=view
            from voxelterrain.building import rotate_xy
            transformed=rotate_xy(probes,16,16,view)
            np.testing.assert_array_equal(BuildingGeometry(b).occupied(transformed),[False,True,False,False])

    def test_roof_triangle_heights_and_queries_agree_for_both_axes_and_views(self):
        from voxelterrain.building import rotate_xy
        for shape in PART_SHAPES:
            for axis in (0,1):
                p=building();b=p["building"]
                b["parts"]=[part("Roof",2,3,5,10,8,6,"#cccccc",shape,axis)]
                for view in range(4):
                    b["view"]=view;g=BuildingGeometry(b)
                    for _,triangle,normal in g.triangles():
                        self.assertAlmostEqual(float(np.linalg.norm(normal)),1)
                        if normal[2]<.01:continue
                        for weights in ((.2,.3,.5),(.4,.2,.4)):
                            q=np.array(weights)@triangle
                            inside=q.copy();inside[2]-=1e-4
                            outside=q.copy();outside[2]+=1e-4
                            self.assertTrue(g.occupied([inside])[0],(shape,axis,view,q))
                            self.assertFalse(g.occupied([outside])[0],(shape,axis,view,q))

    def test_construction_geometry_caps_at_exact_height(self):
        p=building();b=p["building"]
        b["parts"]=[part("Roof",2,2,0,12,12,20,"#cccccc","gable")]
        for stage in range(4):
            g=BuildingGeometry(b,stage=stage)
            for _,triangle,normal in g.triangles():
                self.assertLessEqual(triangle[:,2].max(),g.cutoff+1e-9)
                if normal[2]>.01:
                    q=triangle.mean(axis=0)
                    self.assertTrue(g.occupied([q-[0,0,.0001]])[0])
                    self.assertFalse(g.occupied([q+[0,0,.0001]])[0])

    def test_unequal_footprint_rotates_and_geometry_stays_inside(self):
        p=building("townhouse");b=p["building"]
        for view in range(4):
            b["view"]=view;g=BuildingGeometry(b)
            self.assertEqual((g.width,g.depth),(2,1) if view%2 else (1,2))
            for _,triangle,_ in g.triangles():
                self.assertTrue((triangle[:,:2]>=0).all())
                self.assertTrue((triangle[:,0]<=g.width*16).all())
                self.assertTrue((triangle[:,1]<=g.depth*16).all())

    def test_split_tile_sprites_reassemble_exactly_at_every_zoom_view_and_colour_depth(self):
        p=building("warehouse");p["building"]["parts"][2]["tag"]=202
        for view in range(4):
            p["building"]["view"]=view
            for zoom in (1,2,4):
                r=render(p,zoom=zoom);fragments=building_fragments(r,p["building"],zoom)
                coverage=np.zeros((r.rgb.height,r.rgb.width),dtype=int)
                for field in ("rgb","palette_image","mask"):
                    source=np.asarray(getattr(r,field));assembled=np.zeros_like(source)
                    for x,y,f in fragments:
                        image=np.asarray(getattr(f,field));visible=np.asarray(f.rgb)[:,:,3]>0
                        left=f.offset[0]+32*(y-x)*zoom-r.offset[0]
                        top=f.offset[1]+16*(x+y)*zoom-r.offset[1]
                        if not visible.any():continue
                        dst=assembled[top:top+image.shape[0],left:left+image.shape[1]]
                        dst[visible]=image[visible]
                        if field=="rgb":coverage[top:top+image.shape[0],left:left+image.shape[1]]+=visible
                    np.testing.assert_array_equal(assembled,source)
                np.testing.assert_array_equal(coverage,np.asarray(r.rgb)[:,:,3]>0)

    def test_transparency_courtyard_and_128_pixel_height(self):
        p=building();p["building"]["parts"]=[part("Tower",2,2,0,2,2,128,"#cccccc"),part("Wing",10,10,12,4,4,3,"#aaaaff")]
        p=validate(p);r=render(p)
        self.assertEqual(r.bounds["zextent"],128)
        self.assertIn(-1,np.unique(r.cell_map))
        self.assertEqual(r.clipped,0)

    def test_sprite_texture_projection_preserves_colours_and_company_mask(self):
        p=building();p["light"].update(ambient=1,strength=0,shadows=0,ao=0)
        r=render(p);ref=Reference(r.rgb,r.mask,*r.offset,indexed=False)
        p["texture"]="project";p["texture_light"]=0
        mapped=render(p,ref)
        self.assertEqual(mapped.uncovered,0)
        np.testing.assert_array_equal(np.asarray(mapped.rgb),np.asarray(r.rgb))
        p["texture"]="none"
        p["building"]["parts"][1]["tag"]=202
        masked=render(p)
        self.assertIn(202,np.unique(masked.mask))


class BuildingExportTests(unittest.TestCase):
    def test_legacy_buildings_are_rejected(self):
        with self.assertRaisesRegex(ValueError,"Legacy"):export_bundle([building()],resolve_reference,False,True)

    @unittest.skipUnless(compiler_available(),"NML unavailable")
    def test_all_four_lot_sizes_compile_for_both_features_and_selected_orientations(self):
        projects=[]
        for width,depth in ((1,1),(1,2),(2,1),(2,2)):
            for feature in ("building","house"):
                p=building();p["profile"]=feature;p["name"]=f"{feature} {width}x{depth}"
                p["building"].update(width=width,depth=depth,views=1,view=1)
                p["export_zooms"]=[1];p["colour_mode"]="8bpp";projects.append(p)
        raw,m,d=export_bundle(projects,resolve_reference,True)
        self.assertTrue(m["compiled"])
        source=(d/"workshop.nml").read_text()
        for size in ("1X1","1X2","2X1","2X2"):self.assertIn("HOUSE_SIZE_"+size,source)
        self.assertIn("getbits(extra_callback_info1, 0, 5)",source)
        self.assertIn("accepted_cargos: [[PASS, 4], [MAIL, 2]]",source)
        self.assertNotIn("override:",source)

    @unittest.skipUnless(compiler_available(),"NML unavailable")
    def test_both_features_all_views_stages_zooms_compile_decode_exactly(self):
        try:codec_path()
        except ValueError:self.skipTest("GRFCodec unavailable")
        p=building("townhouse");p["building"]["parts"][1]["tag"]=202
        q=copy.deepcopy(p);q["profile"]="house";q["name"]="Growing town house"
        raw,m,d=export_bundle([p,q],resolve_reference,True)
        self.assertEqual(len(m["sprites"]),264)
        self.assertEqual(m["tiles"][0]["stages"],[3])
        self.assertEqual(m["tiles"][1]["stages"],[0,1,2,3])
        lib=import_grf((d/"workshop.grf").read_bytes(),"buildings.grf")
        decoded=set()
        for s in lib.sprites:
            image,mask=lib.crop(s.key)
            pixels=np.asarray(mask if s.depth=="8bpp" else image).tobytes()
            decoded.add((s.depth,s.zoom,s.width,s.height,s.xoffset,s.yoffset,pixels))
        for r in m["sprites"]:
            source=Image.open(d/r["file"])
            key=(r["mode"],{1:"normal",2:"zi2",4:"zi4"}[r["zoom"]],r["width"],r["height"],r["xoffset"],r["yoffset"],np.asarray(source).tobytes())
            self.assertIn(key,decoded)
        lib.sheet.cache_clear()
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            saved=json.loads(z.read("project.voxel.json"))
            self.assertEqual(saved["current"]["building"],p["building"])
            self.assertEqual(json.loads(z.read("manifest.json"))["grf_sha256"],m["grf_sha256"])
