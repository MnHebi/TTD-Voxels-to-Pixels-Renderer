# SPDX-License-Identifier: GPL-2.0-only
import unittest

from PIL import Image

from voxelterrain.model import default_project
from voxelterrain.palette import PALETTES
from voxelterrain.server import png_data, sample_reference


class DropperTests(unittest.TestCase):
    def project(self, image, mask=None, depth="32bpp", palette="dos"):
        p=default_project()
        p["reference"]={"png":png_data(image),"mask":png_data(mask) if mask else None,
                        "xoffset":-31,"yoffset":-7,"scale":4,"depth":depth,"palette":palette}
        return p

    def test_rgb_sampling_uses_exact_source_coordinates_and_alpha(self):
        image=Image.new("RGBA",(3,2));image.putpixel((2,1),(18,171,52,255))
        p=self.project(image)
        self.assertEqual(sample_reference(p,2,1),{"colour":"#12ab34","alpha":255,"index":None,"tag":0,"palette":"dos"})
        self.assertEqual(sample_reference(p,0,0)["alpha"],0)

    def test_indexed_sampling_preserves_exact_indices_even_when_colours_duplicate(self):
        image=Image.new("P",(3,1));image.putpalette(PALETTES["dos"])
        palette=image.getpalette();palette[203*3:203*3+3]=palette[202*3:202*3+3];image.putpalette(palette)
        image.putdata([202,203,100]);image.info["transparency"]=0
        p=self.project(image,image,"8bpp")
        a,b=sample_reference(p,0,0),sample_reference(p,1,0)
        self.assertEqual(a["colour"],b["colour"])
        self.assertEqual((a["tag"],b["tag"]),(202,203))
        self.assertEqual(sample_reference(p,2,0)["index"],100)
        self.assertEqual(sample_reference(p,2,0)["tag"],0)

    def test_rgb_masks_and_windows_animation_indices_are_retained(self):
        image=Image.new("RGBA",(1,1),(50,70,90,255));mask=Image.new("P",(1,1),100);mask.putpalette(PALETTES["dos"])
        self.assertEqual(sample_reference(self.project(image,mask),0,0)["tag"],100)
        mask.putpixel((0,0),217);mask.putpalette(PALETTES["windows"])
        p=self.project(mask,mask,"8bpp","windows")
        self.assertEqual(sample_reference(p,0,0)["tag"],217)

    def test_invalid_coordinates_and_missing_sources_are_rejected(self):
        p=self.project(Image.new("RGBA",(2,2)))
        for x,y in ((-1,0),(2,0),(0,2),(.5,0),(True,0),(None,0)):
            with self.assertRaises(ValueError):sample_reference(p,x,y)
        with self.assertRaises(ValueError):sample_reference(default_project(),0,0)


if __name__=="__main__":unittest.main()
