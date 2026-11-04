# Third-party components and specifications

The application is GPL-2.0-only. Upstream licences below remain unchanged; the GPL-2.0-or-later components are used under version 2. See LICENSE_NOTICE.md.

- `assets/palettes.json` contains the canonical DOS and Windows TTD palette tables extracted from GRFCodec 6.0.6's PNG output. Both tables were compared byte-for-byte with NML 0.9.0's `raw_palette_data` entries 0 and 1. GRFCodec and NML use GPL-2.0-or-later. [GRFCodec source](https://github.com/OpenTTD/grfcodec), [NML source](https://github.com/OpenTTD/nml).
- Source checkouts invoke GRFCodec as an external executable. Standalone packages build and bundle GRFCodec 6.1.0-g4c71c0a (a pinned upstream snapshot without the old Boost dependency), zlib 1.3.1 and libpng 1.6.50 from pinned source revisions; their notices and exact source archives accompany the package. See tools/build_grfcodec.py and docs/APP_PACKAGES.md.
- Pillow, NumPy and NML are installed as dependencies under their respective licences. Optional browser tests use Playwright; it is not an application dependency.
- Projection, sprite origins, alternative zoom alignment and masks follow the [NewGRF real-sprite specification](https://newgrf-specs.tt-wiki.net/wiki/RealSprites), [NML real sprites](https://newgrf-specs.tt-wiki.net/wiki/NML:Realsprites), and [sprite layouts](https://newgrf-specs.tt-wiki.net/wiki/NML:Spritelayout).
- Lighting follows the [OpenTTD graphics guidance](https://wiki.openttd.org/en/Development/NewGRF/Recommended%20Standards): sunlight from the lower-right, shadows toward the upper-left.
- Mask brightness and its preview follow OpenTTD's [palette functions](https://github.com/OpenTTD/OpenTTD/blob/master/src/palette_func.h) and [ReallyAdjustBrightness](https://github.com/OpenTTD/OpenTTD/blob/master/src/palette.cpp), GPL-2.0-only. Brightness 128 is neutral; the maximum RGB channel supplies mask intensity.
- No decoded source-game sprite is included in the distribution or the self-authored demo.
- The 19 terrain profiles, corner bit meanings and sprite ordering follow OpenTTD's [slope definitions](https://github.com/OpenTTD/OpenTTD/blob/master/src/slope_type.h) and [GetPartialPixelZ / slope-to-sprite table](https://github.com/OpenTTD/OpenTTD/blob/master/src/landscape.cpp), GPL-2.0-only. Geometry uses the continuous planes before the game's integer height sampling.


Building NewGRF definitions were checked against the official NML references for [objects](https://newgrf-specs.tt-wiki.net/wiki/NML:Objects), [houses](https://newgrf-specs.tt-wiki.net/wiki/NML:Houses), [sprite layouts](https://newgrf-specs.tt-wiki.net/wiki/NML:Spritelayout) and [default house substitutes](https://newgrf-specs.tt-wiki.net/wiki/DefaultHouseProps), together with NML 0.9.0's house property validation. Example building geometry and materials are authored for this project; no building artwork is copied from a reference GRF.


The screenshot palette mapper uses the sRGB-to-OKLab matrices published by [Bjorn Ottosson](https://bottosson.github.io/posts/oklab/), whose implementation is offered as public domain (or MIT). Hue-family restrictions, neutral handling, source-frequency histogram and ordered two-colour mixing are implemented for this workshop. Image colour-profile handling uses Pillow's [ImageCms / LittleCMS support](https://pillow.readthedocs.io/en/stable/reference/ImageCms.html).

Standalone packages are built using [PyInstaller](https://pyinstaller.org/), which provides a bootloader licensing exception for bundled applications. Packages include PyInstaller and dependency notices, Python's licence, NML source, the native helper sources, and the application source. Source archives and SHA-256 provenance are recorded in BUNDLE_MANIFEST.json. Native dependencies retain their original licences: zlib uses the zlib licence and libpng uses the PNG Reference Library licence.
