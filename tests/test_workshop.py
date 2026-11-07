# SPDX-License-Identifier: GPL-2.0-only
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile

import numpy as np
from PIL import Image

from voxelterrain.export import compiler_available, export_bundle
from voxelterrain.grf import codec_path, import_grf, parse_nfo, export_references, declared_palette, PLACEHOLDERS
from voxelterrain.runtime import run_tool
from voxelterrain.model import default_project, preset, validate
from voxelterrain.palette import PALETTES, RESERVED, quantize, indexed, display_masked_rgba
from voxelterrain.render import Reference, render
from voxelterrain.server import resolve_reference


class GeometryTests(unittest.TestCase):
    def test_flat_geometry_and_pixel_phase(self):
        expected={1:((64,31),(-31,0)),2:((128,63),(-62,-1)),4:((256,127),(-124,-2))}
        for zoom,(size,offset) in expected.items():
            r=render(default_project(),zoom=zoom)
            self.assertEqual((r.rgb.size,r.offset),(size,offset))
            self.assertEqual(np.count_nonzero(np.asarray(r.rgb)[:,:,3]),1024*zoom*zoom)
        mask=np.asarray(render(default_project()).rgb)[:,:,3]>0
        self.assertEqual(mask.sum(axis=1).tolist(),list(range(4,65,4))+list(range(60,0,-4)))

    def test_three_by_three_has_no_holes_or_overlaps_at_every_zoom(self):
        for zoom in (1,2,4):
            r=render(default_project(),zoom=zoom)
            coverage=np.zeros((240*zoom,480*zoom),dtype=np.uint8)
            mask=(np.asarray(r.rgb)[:,:,3]>0).astype(np.uint8)
            anchor=(200*zoom,20*zoom)
            for x in range(3):
                for y in range(3):
                    left=anchor[0]+2*(y-x)*16*zoom+r.offset[0]
                    top=anchor[1]+(x+y)*16*zoom+r.offset[1]
                    coverage[top:top+mask.shape[0],left:left+mask.shape[1]]+=mask
            self.assertLessEqual(coverage.max(),1)
            yy,xx=np.mgrid[:coverage.shape[0],:coverage.shape[1]]
            sx=(xx-anchor[0]+.5)/zoom-1
            sy=(yy-anchor[1]+1+zoom//2)/zoom
            wx=(sy-sx/2)/2;wy=(sy+sx/2)/2
            expected=(wx>=0)&(wx<48)&(wy>=0)&(wy<48)
            np.testing.assert_array_equal(coverage>0,expected)

    def test_crop_preserves_ground_origin_when_height_changes(self):
        p=default_project();p["profile"]="object"
        a=render(p)
        p["heights"]=[8]*256
        b=render(p)
        self.assertEqual(a.offset[0],b.offset[0])
        self.assertEqual(b.offset[1],a.offset[1]-8)
        self.assertEqual(b.bounds["zextent"],8)
        self.assertEqual((b.bounds["xextent"],b.bounds["yextent"]),(16,16))

    def test_ground_silhouette_clips_tall_geometry(self):
        p=preset(default_project(),"terrace")
        p["heights"]=[v*4 for v in p["heights"]]
        r=render(p)
        self.assertGreater(r.clipped,0)
        self.assertGreaterEqual(r.offset[1],0)
        self.assertLessEqual(r.rgb.height,31)

    def test_picking_map_contains_actual_visible_columns(self):
        p=preset(default_project(),"terrace");p["profile"]="object"
        r=render(p,zoom=4)
        alpha=np.asarray(r.rgb)[:,:,3]
        self.assertTrue(np.all(r.cell_map[alpha>0]>=0))
        self.assertTrue(np.all(r.cell_map[alpha==0]==-1))
        self.assertLess(r.cell_map.max(),256)

    def test_reference_flat_silhouette_uses_correct_phase_at_extra_zoom(self):
        src=render(default_project())
        ref=Reference(src.rgb,None,*src.offset)
        for zoom in (1,2,4):
            r=render(default_project(),ref,zoom)
            expected=render(default_project(),zoom=zoom)
            self.assertEqual(r.offset,expected.offset)
            np.testing.assert_array_equal(np.asarray(r.rgb)[:,:,3],np.asarray(expected.rgb)[:,:,3])
            self.assertEqual(r.missing_ground,0)

    def test_mound_has_complete_flat_ground_footprint(self):
        for zoom in (1,2,4):
            r=render(preset(default_project(),"mound"),zoom=zoom)
            self.assertEqual(r.missing_ground,0)

    def test_lighting_distinguishes_faces(self):
        p=default_project();p["profile"]="object";p["heights"]=[8]*256
        p["light"]["shadows"]=0;p["light"]["ao"]=0
        r=render(p,zoom=4)
        colours=np.unique(np.asarray(r.rgb).reshape(-1,4),axis=0)
        self.assertGreaterEqual(len(colours),4)  # top, both visible sides, transparent


class ColourTests(unittest.TestCase):
    def test_both_palettes_are_complete(self):
        for p in PALETTES.values():
            self.assertEqual(len(p),768)

    def test_quantisation_never_assigns_special_or_transparent_indices(self):
        rng=np.random.default_rng(123)
        rgba=rng.integers(0,256,(48,48,4),dtype=np.uint8);rgba[:,:,3]=255
        for palette in ("dos","windows"):
            for dither in (False,True):
                result=quantize(Image.fromarray(rgba),palette,dither)
                self.assertFalse(set(np.unique(result))&RESERVED[palette])
                self.assertEqual(result.mode,"P")

    def test_alpha_zero_and_explicit_company_indices_are_preserved(self):
        rgba=np.full((2,2,4),255,dtype=np.uint8);rgba[0,0,3]=0
        semantic=np.array([[205,198],[0,205]],dtype=np.uint8)
        result=quantize(Image.fromarray(rgba),semantic=semantic)
        self.assertEqual(np.asarray(result).tolist(),[[0,198],[15,205]])
        self.assertEqual(result.info["transparency"],0)

    def test_projection_reproduces_source_pixels_without_double_lighting(self):
        p=default_project();p["light"].update(ambient=1,strength=0,shadows=0,ao=0)
        p["colours"]=[f'#{(i*7)%256:02x}{(i*13)%256:02x}{(i*19)%256:02x}' for i in range(256)]
        src=render(p)
        ref=Reference(src.rgb,None,*src.offset)
        p["texture"]="project";p["texture_light"]=0
        p["colours"]=["#ff00ff"]*256
        p["light"].update(ambient=.1,strength=.1)
        out=render(p,ref)
        np.testing.assert_array_equal(np.asarray(out.rgb),np.asarray(src.rgb))
        self.assertEqual(out.uncovered,0)

    def test_surface_texture_covers_elevated_surfaces_beyond_projected_image(self):
        src=render(default_project())
        ref=Reference(src.rgb,None,*src.offset)
        p=preset(default_project(),"terrace");p["profile"]="object";p["texture"]="surface"
        p["heights"]=[h*3 for h in p["heights"]]
        surface=render(p,ref)
        p["texture"]="project";projection=render(p,ref)
        self.assertLess(surface.uncovered,projection.uncovered)

    def test_company_colour_generates_rgb_mask_and_indexed_output(self):
        p=default_project();p["tags"]=[202]*256
        r=render(p)
        visible=np.asarray(r.rgb)[:,:,3]>0
        self.assertTrue(np.all(np.asarray(r.mask)[visible]==202))
        self.assertTrue(np.all(np.asarray(r.palette_image)[visible]==202))
        rgb=np.asarray(r.rgb)[visible,:3]
        self.assertTrue(np.all(rgb[:,0]==rgb[:,1]))

    def test_neutral_mask_brightness_is_128_independent_of_palette_shade(self):
        p=default_project();p["tags"]=[202]*256
        p["light"].update(ambient=1,strength=0,shadows=0,ao=0)
        r=render(p)
        visible=np.asarray(r.rgb)[:,:,3]>0
        self.assertTrue(np.all(np.asarray(r.rgb)[visible,:3]==128))
        display=np.asarray(display_masked_rgba(r.rgb,r.mask))
        expected=np.array(PALETTES["dos"]).reshape(256,3)[202]
        self.assertTrue(np.all(display[visible,:3]==expected))

    def test_32bpp_reference_preserves_ordinary_mask_indices_and_brightness(self):
        p=default_project();src=render(p)
        rgba=np.array(src.rgb);visible=rgba[:,:,3]>0
        rgba[visible,:3]=96
        tags=np.where(visible,80,0).astype(np.uint8)
        ref=Reference(Image.fromarray(rgba),indexed(tags),*src.offset,indexed=False)
        p["texture"]="project";p["texture_light"]=0
        r=render(p,ref)
        self.assertTrue(np.all(np.asarray(r.mask)[visible]==80))
        self.assertTrue(np.all(np.asarray(r.rgb)[visible,:3]==96))


class InputTests(unittest.TestCase):
    def test_rejects_nonfinite_and_wrong_sized_models(self):
        p=default_project();p["heights"][1]=float("nan")
        with self.assertRaises(ValueError):validate(p)
        p=default_project();p["colours"].pop()
        with self.assertRaises(ValueError):validate(p)

    def test_nfo_spaces_alternatives_and_mask(self):
        text='''0 C:/a path/sheet.png 8bpp 2 3 64 31 -31 0 normal nocrop
  | C:/a path/sheet.32.png 32bpp 4 5 128 63 -62 -1 zi2 chunked
  | C:/a path/sheet.png mask 8 9
1 * 4 00 00 00 00'''
        s=parse_nfo(text,Path("temp"))
        self.assertEqual(len(s),2)
        self.assertEqual(s[1].number,0)
        self.assertEqual(s[1].mask_x,8)
        self.assertEqual(s[1].mask_y,9)
        self.assertEqual(s[1].image,str(Path("temp/sheet.32.png")))

    def test_declared_palette_from_action14(self):
        header="// Automatically generated by GRFCODEC. Do not modify!\n    0 * 4\t 0B 00 00 00\n"
        # GRFCodec mixes strings and bytes and continues long pseudo-sprites on following lines.
        multiline=header+('    1 * 54\t 14 "CINFOBVRSN" 04 00 01 00 00 00 "BMINV" 04 00 01 00 00 00 "BNPAR" 01\n'
                          '\t 00 00 "BPALS" 01 00 "WBBLTR" 01 00 38 00 00\n'
                          '    2 sprites/a.png 8bpp 0 0 64 31 -31 0 normal')
        self.assertEqual(declared_palette(multiline),"windows")
        self.assertEqual(declared_palette(header+'    1 * 16\t 14 "CINFOBPALS" 01 00 44 00 00'),"dos")
        self.assertEqual(declared_palette(header+'    1 * 16\t 14 "CINFOBPALS" 01 00 "A" 00 00'),"any")
        # Text chunks before PALS are skipped.
        self.assertEqual(declared_palette(header+'    1 * 26\t 14 "CINFOTNAME" 7F "Set" 00 "BPALS" 01 00 "W" 00 00'),"windows")
        # PALS outside INFO, truncated data, unknown values and missing Action 14 are undeclared.
        self.assertIsNone(declared_palette(header+'    1 * 16\t 14 "COTHRBPALS" 01 00 "W" 00 00'))
        self.assertIsNone(declared_palette(header+'    1 * 16\t 14 "CINFOBPALS" 01'))
        self.assertIsNone(declared_palette(header+'    1 * 16\t 14 "CINFOBPALS" 01 00 "X" 00 00'))
        self.assertIsNone(declared_palette(header+'    1 * 3\t 14 00 00'))
        self.assertIsNone(declared_palette(header))
        # NML-style \w, \b and \d escapes.
        escaped=header+('    1 * 54 14 "C" "INFO"\n"B" "VRSN" \\w4 \\dx00000001\n"B" "MINV" \\w4 \\dx00000001\n'
                        '"B" "NPAR" \\w1 00\n"B" "PALS" \\w1 "W"\n"B" "BLTR" \\w1 "8"\n00\n00')
        self.assertEqual(declared_palette(escaped),"windows")
        self.assertIsNone(declared_palette(header+'    1 * 16 14 "CINFOBPALS" \\w99999 "W" 00 00'))

    def test_mask_without_rgb_is_rejected(self):
        with self.assertRaises(ValueError):parse_nfo('| foo.png mask 0 0',Path("temp"))

    def test_texture_requires_a_reference(self):
        p=default_project();p["texture"]="project"
        with self.assertRaises(ValueError):render(p)


class ExportTests(unittest.TestCase):
    def test_individual_files_metadata_and_rgb_fallback(self):
        p=default_project();p["colour_mode"]="32bpp"
        raw,m,d=export_bundle([p],resolve_reference)
        self.assertEqual(len(m["sprites"]),4)
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            for record in m["sprites"]:
                with Image.open(z.open(record["file"])) as image:
                    self.assertEqual(image.size,(record["width"],record["height"]))
                    self.assertEqual(image.mode,"P" if record["mode"]=="8bpp" else "RGBA")
                if record["mode"]=="8bpp":self.assertTrue(record["fallback"])
            self.assertIn("workshop.nml",z.namelist())
        self.assertEqual(m["runtime_status"],"NOT_TESTED_IN_GAME")

    def test_duplicate_ground_targets_are_rejected(self):
        with self.assertRaises(ValueError):export_bundle([default_project(),default_project()],resolve_reference)

    def test_newgrf_local_id_is_not_silently_used_as_a_base_id(self):
        p=default_project();p["replacement_id"]=5000
        with self.assertRaises(ValueError):export_bundle([p],resolve_reference)

    def test_incomplete_ground_footprint_is_rejected(self):
        p=default_project();p["heights"]=[8]*256
        with self.assertRaisesRegex(ValueError,"ground-footprint"):
            export_bundle([p],resolve_reference)

    @unittest.skipUnless(compiler_available(),"NML compiler not installed")
    def test_modern_both_modes_compile_and_decode_with_exact_bounds_and_pixels(self):
        try:codec_path()
        except ValueError:self.skipTest("GRFCodec not installed")
        for profile,palette,mode in (("ground","dos","both"),("object","dos","both"),
                                     ("ground","windows","32bpp"),("object","windows","8bpp")):
            p=preset(default_project(),"mound");p["profile"]=profile;p["tags"][8*16+8]=202
            p["palette"]=palette;p["colour_mode"]=mode
            _,manifest,d=export_bundle([p],resolve_reference,True)
            library=import_grf((d/"workshop.grf").read_bytes(),"roundtrip.grf",palette)
            try:
                self.assertEqual(len(library.sprites),len(manifest["sprites"]))
                reference_zip=export_references(library)
                with zipfile.ZipFile(io.BytesIO(reference_zip)) as archive:
                    references=json.loads(archive.read("manifest.json"))
                    self.assertEqual(len(references["sprites"]),len(library.sprites))
                    self.assertTrue(all(name.startswith("sprites/") for name in archive.namelist() if name.endswith(".png")))
                    for record in references["sprites"]:
                        with Image.open(archive.open(record["file"])) as image:
                            self.assertEqual(image.mode,"P" if record["depth"]=="8bpp" else "RGBA")
                            self.assertEqual(image.size,(record["width"],record["height"]))
                for record in manifest["sprites"]:
                    match=[s for s in library.sprites if s.depth==record["mode"] and s.zoom=={1:"normal",2:"zi2",4:"zi4"}[record["zoom"]]]
                    self.assertEqual(len(match),1)
                    s=match[0];image,mask=library.crop(s.key)
                    self.assertEqual((s.width,s.height,s.xoffset,s.yoffset),(record["width"],record["height"],record["xoffset"],record["yoffset"]))
                    source=Image.open(d/record["file"])
                    if source.mode=="P":
                        # Compare palette indices, independently of decoder display colours.
                        np.testing.assert_array_equal(np.asarray(library.sheet(s.image).crop((s.x,s.y,s.x+s.width,s.y+s.height))),np.asarray(source))
                    else:
                        np.testing.assert_array_equal(np.asarray(image),np.asarray(source))
                    if record.get("mask"):
                        self.assertIsNotNone(mask)
                        np.testing.assert_array_equal(np.asarray(mask),np.asarray(Image.open(d/record["mask"])))
            finally:library.sheet.cache_clear()

    @unittest.skipUnless(compiler_available(),"NML compiler not installed")
    def test_import_uses_declared_palette_unless_overridden(self):
        try:codec_path()
        except ValueError:self.skipTest("GRFCodec not installed")
        for palette in ("dos","windows"):
            p=default_project();p["palette"]=palette;p["colour_mode"]="8bpp"
            _,_,d=export_bundle([p],resolve_reference,True)
            payload=(d/"workshop.grf").read_bytes()
            lib=import_grf(payload,"auto.grf")
            self.assertEqual((lib.palette,lib.declared),(palette,palette))
            other="windows" if palette=="dos" else "dos"
            forced=import_grf(payload,"forced.grf",other)
            self.assertEqual((forced.palette,forced.declared),(other,palette))
            # The detected decode matches decoding explicitly with the declared palette.
            exact=import_grf(payload,"exact.grf",palette)
            a,b,c=(library.sheet(library.sprites[0].image).getpalette() for library in (lib,exact,forced))
            self.assertEqual(a,b)
            self.assertNotEqual(a,c)
            for library in (lib,forced,exact):library.sheet.cache_clear()
        with self.assertRaises(ValueError):import_grf(payload,"bad.grf","any")

    def test_undeclared_palette_is_inferred_from_placeholder_indices(self):
        """Base sets such as trg1r.grf have no Action 14; their pixels identify the palette."""
        try:codec=codec_path()
        except ValueError:self.skipTest("GRFCodec not installed")
        self.assertEqual(PLACEHOLDERS["dos"].tolist(),list(range(215,227)))
        self.assertEqual(PLACEHOLDERS["windows"].tolist(),[*range(1,10),*range(246,255)])
        # Windows art uses DOS-magenta indices; DOS art uses Windows-magenta ones. One stray pixel is tolerated.
        cases=(("windows",[*range(215,227)]*8+[1]),("dos",[*range(246,255)]*8+[220]),(None,[100]*64+[220]*3))
        for expected,used in cases:
            with tempfile.TemporaryDirectory() as tmp:
                d=Path(tmp);(d/"sprites").mkdir()
                image=Image.new("P",(16,8),100);image.putpalette(PALETTES["dos"])
                image.putdata(used+[100]*(128-len(used)))
                image.save(d/"sprites/a.png",transparency=0)
                # GRFCodec reads the info version from the second line.
                (d/"workshop.nfo").write_text("// Undeclared palette fixture\n// (Info version 32)\n"
                                              "// Format: spritenum imagefile depth xpos ypos xsize ysize xrel yrel zoom flags\n"
                                              "0 * 4 01 00 00 00\n1 sprites/a.png 8bpp 0 0 16 8 0 0 normal nocrop\n")
                result=run_tool([codec,"-s","-e","-g","1",str(d/"workshop.grf"),str(d)],cwd=d,capture_output=True,timeout=120)
                self.assertEqual(result.returncode,0,result.stdout)
                payload=(d/"workshop.grf").read_bytes()
            lib=import_grf(payload,"undeclared.grf")
            try:
                self.assertEqual((lib.declared,lib.inferred,lib.palette),(None,expected,expected or "dos"))
                s=lib.sprites[0]
                self.assertEqual(np.asarray(lib.sheet(s.image))[s.y,s.x:s.x+16].tolist(),used[:16])
                # An explicit choice is still honoured.
                forced=import_grf(payload,"forced.grf","dos")
                self.assertEqual((forced.palette,forced.inferred),("dos",expected))
            finally:lib.sheet.cache_clear()

    def test_legacy_v1_8bpp_roundtrip(self):
        try:codec_path()
        except ValueError:self.skipTest("GRFCodec not installed")
        p=default_project();p["colour_mode"]="8bpp"
        _,m,d=export_bundle([p],resolve_reference,True,True)
        self.assertEqual(len(m["sprites"]),1)
        self.assertNotEqual((d/"workshop.grf").read_bytes()[:2],b"\0\0")
        lib=import_grf((d/"workshop.grf").read_bytes(),"legacy.grf")
        self.assertEqual(len(lib.sprites),1)
        self.assertEqual((lib.sprites[0].xoffset,lib.sprites[0].yoffset),(-31,0))


if __name__=="__main__":unittest.main()
