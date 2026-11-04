# SPDX-License-Identifier: GPL-2.0-only
import base64
import io
import unittest

import numpy as np
from PIL import Image, ImageCms

from voxelterrain.model import default_project, validate
from voxelterrain.palette import PALETTES, RESERVED, oklab, quantize
from voxelterrain.pictures import import_picture, picture_image, convert_picture, validate_pictures


def payload(image, format="PNG", **options):
    out=io.BytesIO();image.save(out,format=format,**options);return out.getvalue()


class PictureImportTests(unittest.TestCase):
    def test_supported_screenshot_formats_and_reference_copy_preserve_colours(self):
        for fmt in ("PNG","BMP","WEBP"):
            source=Image.new("RGB",(25,10),(96,112,88))
            p=import_picture(payload(source,fmt,**({"lossless":True} if fmt=="WEBP" else {})),"Example "+fmt)
            self.assertEqual((p["width"],p["height"]),(25,10))
            self.assertEqual(picture_image(p["png"]).getpixel((12,5)),(96,112,88,255))
            self.assertFalse(p["resized"])
        jpeg=import_picture(payload(source,"JPEG"))
        self.assertEqual((jpeg["width"],jpeg["height"]),(25,10))

    def test_size_cap_alpha_orientation_and_profile(self):
        image=Image.new("RGBA",(2000,1000),(12,171,52,123))
        p=import_picture(payload(image));im=picture_image(p["png"])
        self.assertEqual(im.size,(1600,800));self.assertTrue(p["resized"])
        self.assertEqual(im.getpixel((400,300))[3],123)
        oriented=Image.new("RGB",(20,10));exif=Image.Exif();exif[274]=6
        p=import_picture(payload(oriented,"JPEG",exif=exif));self.assertEqual((p["width"],p["height"]),(10,20))
        image=Image.new("RGB",(2,2),(96,112,88))
        profile=ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        im=picture_image(import_picture(payload(image,icc_profile=profile))["png"])
        self.assertEqual(im.getpixel((0,0)),(96,112,88,255))

    def test_picture_deck_validation_and_invalid_uploads(self):
        p=import_picture(payload(Image.new("RGBA",(2,2))))
        self.assertEqual(len(validate_pictures([p,p])),2)
        with self.assertRaises(ValueError):validate_pictures([p]*13)
        with self.assertRaises(ValueError):import_picture(b"this is not a screenshot")
        with self.assertRaises(ValueError):picture_image("not-base64")
        with self.assertRaises(ValueError):convert_picture(p["png"],"invalid")

    def test_converted_download_is_indexed_and_uses_canonical_palette(self):
        p=import_picture(payload(Image.new("RGBA",(8,8),(96,112,88,255))))
        for palette in PALETTES:
            result=convert_picture(p["png"],palette)
            self.assertEqual(result.mode,"P")
            self.assertEqual(result.getpalette(),PALETTES[palette])
            self.assertFalse(set(np.unique(result))&RESERVED[palette])


class BalancedPaletteTests(unittest.TestCase):
    def test_oklab_reference_values(self):
        # Known sRGB primary values from the published transformation.
        actual=oklab([[0,0,0],[255,255,255],[255,0,0],[0,255,0],[0,0,255]])
        expected=[[0,0,0],[1,0,0],[.627955,.224863,.125846],[.866440,-.233888,.179498],[.452014,-.032457,-.311528]]
        np.testing.assert_allclose(actual,expected,atol=1e-6)

    def test_muted_greens_retain_hue_instead_of_turning_yellow_brown(self):
        rgb=np.array([[[48,72,56],[96,112,88],[112,128,104],[128,144,120]]],dtype=np.uint8)
        image=Image.fromarray(rgb).convert("RGBA")
        source=oklab(rgb)[0];hue=lambda lab:np.degrees(np.arctan2(lab[:,2],lab[:,1]))
        errors=[]
        for mapping in ("nearest","balanced"):
            lab=oklab(np.asarray(quantize(image,mapping=mapping).convert("RGB")))[0]
            errors.append(np.abs((hue(lab)-hue(source)+180)%360-180))
        self.assertGreater(errors[0].mean(),30)
        self.assertLess(errors[1].mean(),12)

    def test_neutral_ramp_remains_neutral_and_dithering_improves_average_tone(self):
        rgba=np.tile(np.arange(256,dtype=np.uint8)[None,:,None],(8,1,4));rgba[:,:,3]=255
        result=np.asarray(quantize(Image.fromarray(rgba),mapping="balanced",dither=True).convert("RGB"))
        self.assertLessEqual(np.ptp(result.astype(int),axis=2).max(),4)
        image=Image.new("RGBA",(64,64),(145,145,145,255));target=oklab([[145,145,145]])[0,0]
        errors=[]
        for dither in (False,True):
            rgb=np.asarray(quantize(image,mapping="balanced",dither=dither).convert("RGB"))
            errors.append(abs(oklab(rgb)[:,:,0].mean()-target))
        self.assertLess(errors[1],errors[0]/2)

    def test_alpha_semantics_palette_exactness_and_determinism_for_both_palettes(self):
        for palette in PALETTES:
            colours=np.array(PALETTES[palette],dtype=np.uint8).reshape(256,3)
            allowed=[i for i in range(256) if i not in RESERVED[palette]]
            rgba=np.concatenate([colours[allowed][None,:,:],np.full((1,len(allowed),1),255,dtype=np.uint8)],axis=2)
            im=Image.fromarray(rgba)
            for dither in (False,True):
                output=quantize(im,palette,dither,mapping="balanced")
                np.testing.assert_array_equal(np.asarray(output.convert("RGB")),rgba[:,:,:3])
                self.assertFalse(set(np.unique(output))&RESERVED[palette])
            rgba[0,0,3]=0;tags=np.zeros(rgba.shape[:2],dtype=np.uint8);tags[0,1]=202
            output=quantize(Image.fromarray(rgba),palette,True,tags,"balanced")
            self.assertEqual(output.getpixel((0,0)),0);self.assertEqual(output.getpixel((1,0)),202)
            np.testing.assert_array_equal(output,quantize(Image.fromarray(rgba),palette,True,tags,"balanced"))

    def test_photo_histogram_path_keeps_exact_palette_colours_and_excludes_effects(self):
        rng=np.random.default_rng(7);rgb=rng.integers(0,256,(220,200,4),dtype=np.uint8);rgb[:,:,3]=255
        palette=np.array(PALETTES["dos"],dtype=np.uint8).reshape(256,3)
        rgb[0,:200,:3]=palette[:200]
        image=Image.fromarray(rgb);result=quantize(image,mapping="balanced",dither=True)
        for i in range(1,198):self.assertEqual(result.convert("RGB").getpixel((i,0)),tuple(palette[i]))
        self.assertFalse(set(np.unique(result))&RESERVED["dos"])

    def test_old_projects_keep_original_mapping_and_bad_options_fail(self):
        p=default_project();p.pop("palette_mapping")
        self.assertEqual(validate(p)["palette_mapping"],"nearest")
        p["palette_mapping"]="invalid"
        with self.assertRaises(ValueError):validate(p)
        with self.assertRaises(ValueError):quantize(Image.new("RGBA",(1,1)),mapping="invalid")
