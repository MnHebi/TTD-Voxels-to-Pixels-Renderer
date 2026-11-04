# SPDX-License-Identifier: GPL-2.0-only
"""Independent surface, seam, migration and export checks for shaped terrain."""
import io
import json
import unittest
import zipfile

import numpy as np
from PIL import Image

from voxelterrain.geometry import Geometry,SHAPES,SLOPE_NAMES,ttd_height
from voxelterrain.model import default_project,preset,validate,resize,replacement_target
from voxelterrain.render import render
from voxelterrain.export import export_bundle,compiler_available
from voxelterrain.grf import codec_path,import_grf
from voxelterrain.server import resolve_reference


class ShapeGeometryTests(unittest.TestCase):
    def test_old_projects_migrate_without_geometry_changes(self):
        for n in (8,16,32):
            old=default_project()
            for key in ("shapes","rotations","rises","terrain_slope","terrain_base"):old.pop(key)
            old.update(size=n,heights=[0]*(n*n),colours=["#648b39"]*(n*n),tags=[0]*(n*n))
            new=validate(old)
            self.assertEqual(new["shapes"],["cube"]*(n*n))
            self.assertEqual(render(new).rgb.size,(64,31))

    def test_shape_validation_and_rise_limit(self):
        for key,value in (("shapes","unknown"),("rotations",4),("rises",float("nan"))):
            p=default_project();p[key][0]=value
            with self.assertRaises(ValueError):validate(p)
        p=default_project();p["shapes"][0]="wedge";p["heights"][0]=64
        with self.assertRaisesRegex(ValueError,"Shape top"):validate(p)

    def test_cap_shapes_have_their_actual_surfaces_and_normals(self):
        for shape in SHAPES:
            for rotation in range(4):
                p=default_project();p["shapes"][0]=shape;p["rotations"][0]=rotation;p["rises"][0]=2
                geometry=Geometry(p)
                for tri in geometry.triangles(0):
                    normal=np.cross(tri[1]-tri[0],tri[2]-tri[0])
                    self.assertGreater(normal[2],0)
                    # Test interior points of triangles against an independent
                    # barycentric height. This catches wrong hinge diagonals.
                    for weights in ((.2,.3,.5),(.6,.2,.2)):
                        point=np.array(weights)@tri
                        self.assertAlmostEqual(float(geometry.height(point[0],point[1])),point[2],places=9)
                if shape!="cube":self.assertEqual(geometry.maximum,2)

    def test_ridge_and_valley_with_identical_corners_are_distinct(self):
        p=default_project();p["rises"][0]=2
        p["shapes"][0]="ridge";ridge=Geometry(p)
        p["shapes"][0]="valley";valley=Geometry(p)
        np.testing.assert_array_equal(ridge.corners,valley.corners)
        self.assertEqual(float(ridge.height(.5,.5)),2)
        self.assertEqual(float(valley.height(.5,.5)),0)

    def test_all_19_presets_match_continuous_engine_planes_at_all_grids(self):
        rng=np.random.default_rng(34)
        x,y=rng.uniform(0,16,(2,300))
        for n in (8,16,32):
            for slope in SLOPE_NAMES:
                p=default_project();p=resize(p,n);p=preset(p,"ttd_"+str(slope))
                g=Geometry(p)
                np.testing.assert_allclose(g.height(x,y),ttd_height(slope,x,y),atol=1e-9,
                                           err_msg=f"slope {slope}, grid {n}")
                c=g.corners.reshape(n,n,4)
                np.testing.assert_allclose(c[:,:-1,1],c[:,1:,0],atol=1e-9)
                np.testing.assert_allclose(c[:,:-1,2],c[:,1:,3],atol=1e-9)
                np.testing.assert_allclose(c[:-1,:,3],c[1:,:,0],atol=1e-9)
                np.testing.assert_allclose(c[:-1,:,2],c[1:,:,1],atol=1e-9)

    def test_steep_corner_bit_meanings(self):
        # bits W=1 S=2 E=4 N=8; steep S has W+S+E+16=23.
        corners=(np.array([0,16,16,0]),np.array([0,0,16,16]))
        np.testing.assert_array_equal(ttd_height(23,*corners),[0,8,16,8])
        np.testing.assert_array_equal(ttd_height(27,*corners),[8,16,8,0])
        np.testing.assert_array_equal(ttd_height(29,*corners),[16,8,0,8])
        np.testing.assert_array_equal(ttd_height(30,*corners),[8,0,8,16])

    def test_resize_preserves_native_slopes_and_materials(self):
        p=preset(default_project(),"ttd_10");p["colours"]=["#123456"]*256
        for n in (32,8,16):
            p=resize(p,n)
            self.assertEqual(p["colours"],["#123456"]*(n*n))
            np.testing.assert_allclose(Geometry(p).height(3.4,8.1),ttd_height(10,3.4,8.1))
        p["heights"][0]+=1
        with self.assertRaisesRegex(ValueError,"custom shapes"):resize(p,32)

    def test_ground_offsets_match_ttd_family_for_every_zoom(self):
        extents={0:(31,0),1:(31,0),2:(23,0),3:(23,0),4:(31,0),5:(31,0),6:(23,0),7:(23,0),
                 8:(39,-8),9:(39,-8),10:(31,-8),11:(31,-8),12:(39,-8),13:(39,-8),14:(31,-8),
                 23:(15,0),27:(31,-8),29:(47,-16),30:(31,-8)}
        for slope,(height,yoff) in extents.items():
            p=preset(default_project(),"ttd_"+str(slope))
            for zoom in (1,2,4):
                r=render(p,zoom=zoom)
                self.assertEqual(r.offset,(-31*zoom,yoff*zoom-zoom//2),(slope,zoom))
                self.assertEqual(r.rgb.size,(64*zoom,(height+1)*zoom-1),(slope,zoom))
                self.assertEqual(r.missing_ground,0)

    def test_caps_change_lighting_and_sorting_height(self):
        p=default_project();p["profile"]="object";p["rises"]=[8]*256;p["shapes"]=["pyramid"]*256
        p["light"].update(shadows=0,ao=0)
        r=render(p,zoom=4)
        self.assertEqual(r.bounds["zextent"],8)
        colours=np.unique(np.asarray(r.rgb).reshape(-1,4),axis=0)
        self.assertGreaterEqual(len(colours),4)

    def test_ramp_tiles_join_in_3d_without_pixel_gaps_or_overlaps(self):
        # A 3x3 NE ramp patch, including per-tile elevation, forms one plane.
        for zoom in (1,2,4):
            p=preset(default_project(),"ttd_12");r=render(p,zoom=zoom)
            self.assertEqual(r.tiling["delta_x"],-8)
            self.assertTrue(r.tiling["compatible"])
            mask=(np.asarray(r.rgb)[:,:,3]>0).astype(np.uint8)
            cov=np.zeros((160*zoom,300*zoom),dtype=np.uint8)
            ax,ay=130*zoom,45*zoom
            for x in range(3):
                for y in range(3):
                    z=-8*x
                    left=ax+32*(y-x)*zoom+r.offset[0]
                    top=ay+(16*(x+y)-z)*zoom+r.offset[1]
                    cov[top:top+mask.shape[0],left:left+mask.shape[1]]+=mask
            self.assertLessEqual(cov.max(),1)
            yy,xx=np.mgrid[:cov.shape[0],:cov.shape[1]]
            sx=(xx-ax+.5)/zoom-1;sy=(yy-ay+1+zoom//2)/zoom
            # sx=2*(Y-X), sy=1.5*X+Y-8 for the assembled plane.
            wx=(sy+8-sx/2)/2.5;wy=wx+sx/2
            expected=(wx>=0)&(wx<48)&(wy>=0)&(wy<48)
            np.testing.assert_array_equal(cov>0,expected)

    def test_nonrepeatable_corners_are_flagged(self):
        p=preset(default_project(),"ttd_8")
        self.assertFalse(Geometry(p).tiling()["compatible"])


class ShapeExportTests(unittest.TestCase):
    @unittest.skipUnless(compiler_available(),"NML compiler not installed")
    def test_all_19_ground_slopes_compile_and_keep_exact_sprite_pixels(self):
        try:codec_path()
        except ValueError:self.skipTest("GRFCodec not installed")
        projects=[preset(default_project(),"ttd_"+str(s)) for s in SLOPE_NAMES]
        for i,p in enumerate(projects):p["name"]=str(i)+" "+SLOPE_NAMES[p["terrain_slope"]]
        raw,m,d=export_bundle(projects,resolve_reference,True)
        self.assertEqual(sorted(t["replacement_id"] for t in m["tiles"]),list(range(3981,4000)))
        lib=import_grf((d/"workshop.grf").read_bytes(),"slopes.grf")
        # NML may deduplicate equal sprites. Compare every output's content to
        # the independently decoded set, including its offsets and zoom.
        decoded=set()
        for s in lib.sprites:
            image,mask=lib.crop(s.key)
            pixels=np.asarray(mask if s.depth=="8bpp" else image).tobytes()
            decoded.add((s.depth,s.zoom,s.width,s.height,s.xoffset,s.yoffset,pixels))
        for record in m["sprites"]:
            image=Image.open(d/record["file"])
            signature=(record["mode"],{1:"normal",2:"zi2",4:"zi4"}[record["zoom"]],record["width"],record["height"],record["xoffset"],record["yoffset"],np.asarray(image).tobytes())
            self.assertIn(signature,decoded)
        with zipfile.ZipFile(io.BytesIO(raw)) as z:self.assertEqual(len([f for f in z.namelist() if f.endswith('.png')]),114)

    def test_shape_rises_are_included_in_object_nml_bounds(self):
        p=default_project();p["profile"]="object";p["shapes"]=["pyramid"]*256;p["rises"]=[6]*256
        _,m,d=export_bundle([p],resolve_reference)
        self.assertEqual(m["tiles"][0]["sorting_bounds"]["zextent"],6)
        self.assertIn('zextent: 6;', (d/'workshop.nml').read_text())


if __name__=="__main__":unittest.main()
