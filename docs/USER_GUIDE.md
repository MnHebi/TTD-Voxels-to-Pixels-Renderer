# Detailed user guide

A local editor for OpenTTD terrain, decorative buildings, and growing town houses. Sculpt terrain columns or assemble solid building parts, with GRF and screenshot references, baked lighting, optional sprite textures, and separate PNG exports.

Run commands below from the repository root. Double-click **Start Workshop.cmd** on Windows. The launcher opens the workshop at **http://127.0.0.1:7865/**. Keep its terminal running; close it or press Ctrl+C to stop the server. The workshop binds to this computer only and uses no external web services.

## Setup

Python 3.10 or newer, Pillow, and NumPy are required. NML enables compiled modern NewGRF exports. The Windows launcher also recognises the bundled Codex Python runtime when available.

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe app.py
```

On other systems, use `python3 -m venv .venv` and `.venv/bin/python`. The UI needs a current browser with Canvas and Pointer Events. No Node build or package installation is required for the application.

For GRF import and legacy compilation, obtain [GRFCodec](https://www.openttd.org/downloads/grfcodec-releases/latest). Configure it using:

```powershell
py -3 tools/configure.py --grfcodec "C:\path\to\grfcodec.exe"
```

Alternatively set `GRFCODEC`, put it on PATH, or place the executable in `tools/`. Its path is saved only in the ignored `local.json`. GRFCodec is an external dependency, not bundled. The renderer can be used without it.

## Workflow

1. Drop a `.grf` into the reference library. With **Source palette → Auto** (the default), the palette comes from the GRF's own Action 14 `INFO/PALS` declaration; GRFs that declare no palette, or "any" palette, such as the original `trg*.grf` base sets, are identified from their 8bpp pixels: art that uses many indices which are unused magenta in one palette belongs to the other. Without a clear majority the import falls back to DOS. The import message says which applied. Choose **TTD DOS** or **TTD Windows** to override the declaration; you are warned when your choice differs from it. GRFCodec decodes both container versions. Browse by sprite number; each zoom/depth variant is listed separately. "Tile-sized" is a dimension filter, not semantic tile recognition. **Export selected** or **Export all** extracts original references as individual PNGs with a metadata manifest; indexed pixels and 32bpp masks are preserved.
2. Select a reference. Its image, original offsets, depth, zoom and source hash stay attached to the project. It does **not** automatically become a base-game replacement target: arbitrary NewGRF sprite numbers are local to their source.
3. Choose flat, mound, terrace, a smooth ramp, or any of the **19 TTD terrain shapes**. Use an 8×8, 16×16 or 32×32 grid. Sculpt in the height map or click visible surfaces in the isometric view. R/L/P/F/G/M select Raise/Lower/Paint/Level/Shape/Material; I selects the pixel dropper; right-drag lowers. Ctrl+Z and Ctrl+Y undo/redo model edits. Scroll over the preview to zoom.
4. Use **Reference only**, **Project original sprite**, or **Map onto ground surface**. Projection uses the source camera and origin; surface mapping removes the model height from the lookup and treats the source as a ground-plane texture. Uncovered surfaces retain their painted material. A single reference cannot recover hidden geometry or unseen textures.
5. Set lighting and colour output. Inspect **Tiling** and **Compare**, and optionally enable the origin/bounds overlay. Add finished tiles to the collection to export a batch.
6. Save the editable project, or export the current tile/collection. A ZIP is a convenient folder package: **every sprite inside it is an individual PNG**, never a sprite sheet. The complete unpacked export also remains in `.work/exports/`.

**Save project** includes reference PNG pixels and indexed masks, so reopening it does not depend on temporary decoder files. Local browser storage autosaves the current project and collection. Imported GRF libraries are session-local and can be re-imported. Model undo does not undo collection additions/removals.

## Shapes and terrain presets (0.2)

**Voxel shape** offers cube/flat, wedge, diagonal ramp, outer corner, inner corner, ridge, valley and pyramid caps. Choose a shape, its rotation and **cap rise**, then use the Shape brush (G). T rotates the brush in 90-degree steps. **Apply shape to whole tile** changes every cap while keeping each cell's base height and material. Raising/lowering moves a cap without changing its profile. The top limit is 64 game pixels, including the rise.

Caps are real piecewise-planar surfaces. Their face normals drive lighting; shadow and ambient-occlusion samples use their actual heights. Ridges and valleys use different hinge diagonals even when their corner heights are the same. Existing saved projects without shape data open as cubes.

**TTD terrain shape → Apply** constructs a complete, continuous tile from adjoining caps: flat; four single raised corners; four straight ramps; four three-corner slopes; two opposite-corner valleys; and four steep slopes. Terrain elevations use 8 pixels per level, with steep peaks reaching 16. These presets work at all supported grid sizes and carry their own ground silhouette, so a reference is optional.

For a ground preset, **Terrain family base** identifies the flat sprite of a standard 19-sprite TTD terrain family. The default 3981 selects the grass family, sprites 3981–3999. The exporter applies OpenTTD's slope-to-sprite ordering, including the special steep-slope order. The computed target appears in Base sprite ID. Use **Custom / reference footprint → Apply** to return to a manual target and reference/flat silhouette.

Unedited TTD presets resize exactly, including materials; cubic models retain the existing grid resampling. Choose the grid before sculpting custom caps: resizing an edited shaped model stops with a message rather than changing its slopes silently.

**Tiling** checks opposite edge profiles. Repeatable ramps include the required per-tile elevation, forming a continuous incline. Corner/valley shapes which need complementary neighbours are labelled accordingly. The preview composites at sprite resolution before scaling, avoiding display-only cracks between tiles.

Generate the complete self-authored grass replacement family and a review board:

```powershell
.venv\Scripts\python.exe tools/export_slopes.py --build
```

This creates `exports/ttd-slopes.zip` with 114 individual 8bpp/RGBA PNGs, source/metadata and a compiled GRF, plus `exports/ttd-slope-showcase.png`. Add `--legacy` for normal-zoom 8bpp/container-v1 output. The PNG board is a review illustration; it is not used as a sprite sheet.

## Buildings and town houses (0.3)

Choose **Placement → Decorative building** or **Growing town house**. Both use an independent parts model, so your terrain heightfield remains available when switching back. Choose **Cottage**, **Town house**, **Office**, **Warehouse**, or **Empty lot**, then **Create**. Creating a preset replaces the current parts; Undo restores them. Each part is a solid box, gable roof, hip roof, or shed roof. Use separate parts for walls, floors, balconies, windows, doors, chimneys, and roof details. Parts can overlap; space beneath raised floors and between wings stays empty.

Select a part in the sprite, unrotated plan, or parts list. Set its position, dimensions, shape, roof axis, colour, palette effect, and visibility, then **Apply part changes**. Add, duplicate, and delete parts freely; Undo/Redo also works for buildings. **Paint selected part** applies the palette swatch/effect brush. Hidden parts stay editable and are omitted from geometry, shadows, bounds and exports. An empty lot is transparent until you add parts. Up to 160 parts are supported.

Lots support **1×1, 1×2, 2×1, and 2×2 tiles**. X and Y use 16 units per tile; Z and part height use normal-zoom pixels. Buildings may reach 128 pixels. Parts must stay inside the lot; roofs and balconies may extend past walls within that lot. Shrinking a lot rejects parts that would fall outside it. **View ↻** rotates the geometry in 90-degree steps, recomputing face lighting and shadows from the same world sun. Rectangular lots swap width and depth in odd views. References retain the origin/projection selected by the author; they are not automatically reprojected from one view to another.

**Decorative buildings** export as placeable NewObjects with one or four selectable views. **Growing town houses** export as FEAT_HOUSES with population, mail generation, passenger/mail acceptance, first/last construction year, and growth weight. The last year supports 65535. Houses are additional types rather than replacements for default houses, available in all climates and town zones on flat lots. Acceptance is measured in eighths **per tile**; population and mail generation are set once for the complete house. Each enabled orientation is a separate house variation; the growth weight applies to each variation. Actual growth also depends on OpenTTD's town rules and available lots.

The **Construction preview** shows four height-based stages: 20%, 45%, 70%, and the complete building. Stage geometry clips exactly at the height limit and includes the cut surface; roofs/details appear as construction reaches them. House exports always contain all four stages. Object exports always contain the finished building, regardless of the preview stage. These are generated progressive construction models; scaffolding is not generated automatically.

All existing colour, palette-mask, lighting, reference, projected-texture, comparison, collection, save/open and individual-PNG workflows apply to buildings. Exports render and light the complete scene first, then split visible pixels by their world tile. Each tile/view/stage/zoom/depth is an independent PNG with the correct tile-local north-corner offset. Splitting introduces no artificial walls at tile boundaries, and fragments reassemble exactly, including palette indices and masks. Objects also receive a separate complete purchase preview.

The generated layouts use conservative **16×16 sorting boxes per tile**, with height derived from geometry; a box never extends across the lot's internal tile boundaries. Image rectangles are cropped to actual visible pixels. The manifest distinguishes the sorting volume from image bounds. Generated NML selects fragments by relative tile position and provides suitable substitute house IDs for each footprint. The flat-land restriction uses the object callback's slope parameter before construction. Compiling/loading a GRF does not verify live visual sorting, passenger/mail production, construction timing, or town-growth behaviour.

Generate the original example collection (four objects and sixteen growing house orientations):

```powershell
.venv\Scripts\python.exe tools/export_buildings.py --build
```

This creates `exports/buildings.zip`, with individual sprite PNGs, editable projects, NML/NFO, manifest and test GRF, plus `exports/building-showcase.png`. Legacy 8bpp/container-v1 export remains restricted to ground replacements.

## Screenshot reference window and colour-preserving palettes (0.4)

**Reference pictures** in the top bar opens an optional, nonmodal window. Move it by the title bar and resize it from the corner. Add multiple PNG, JPEG, WebP, BMP or GIF files, drag them into its image area, or paste a clipboard image while the window is focused. It holds up to **12 pictures**. Cycle using the arrows, thumbnails, image selector, or Left/Right when the window has focus. Closing the window hides it; Remove deletes the selected reference.

Choose **Original RGB**, **8bpp · Keep colour families**, or **8bpp · Nearest RGB**, with either DOS or Windows colours. **Compare** shows the prepared RGB reference and converted result side by side. Optional ordered dithering mixes eligible shades to better preserve local tone. **Pick colour / I** works on either image. **Save 8bpp PNG** downloads the selected conversion as a genuinely indexed PNG with the canonical palette and index 0 transparency.

Each pane has its own **− / +** buttons above it, plus **Fit** to reset zoom and centre the image. Drag an enlarged image to pan within that pane; the other pane remains independent. Enlarged pixels are shown sharply, and the dropper still picks the correct source pixel after zooming/panning. Zoom and pan settings persist with the picture-window settings in local storage and saved projects. Zoom changes only the view; conversion and PNG export resolution stay the same.

**Keep colour families** uses OKLab lightness, chroma and hue, rather than raw RGB distance alone. It constrains chromatic colours to nearby available hue families and keeps near-neutral tones on neutral palette entries. Dithering mixes two eligible colours without adding colours outside the game palette or inventing company/animation indices. Large photographic inputs use a bounded 5-bit histogram with frequency-weighted source colours; exact ordinary palette colours remain exact. This aims to reduce green-to-yellow/brown shifts and unwanted grey tinting. It cannot recreate colours absent from the fixed palette, and can trade brightness/saturation accuracy for hue preservation. Compare the result before using it.

The same choice is available under **Colour output → 8bpp matching** for terrain/building rendering and exports. Existing projects default to **Nearest RGB**, preserving their previous conversion. RGB/32bpp source colours are not quantised. Explicit palette-effect tags remain intact in both matching modes.

Picture copies are kept separate from the frequently rendered voxel model and from GRF sprite references. They are **visual references and colour sources**, not automatically aligned game textures. They autosave locally using IndexedDB and are embedded once in **Save project** files with the selected image and window/conversion settings. Reopening a saved project restores them. Sprite-export bundles do not include these screenshot references. Picture additions/removals are independent of model Undo/Redo.

Limits: 24 MiB and 16 million decoded pixels per imported file; reference copies fit within **1600×1600** without enlarging small images. Embedded ICC profiles are converted to sRGB, EXIF orientation is applied, and untagged images are treated as sRGB; source files are unchanged. Animated GIFs use their first frame. The gallery has a 64 MiB encoded-data limit, and project files may be up to 96 MiB. The colour/mapping algorithm does not recover materials, lighting or hidden geometry from a screenshot.

## Sprite colour dropper (0.3.1)

Click **Dropper** or press **I**, then click an opaque pixel in the sprite preview, the original reference in **Compare**, or a library thumbnail. The dropper samples original image pixels rather than the grid, selection/bounds lines, thumbnail letterboxing, or the blended overlay. In Tiling mode it works on every repeated sprite. Transparent pixels leave the current colour unchanged. A successful pick fills the paint colour and returns to Paint; **Esc** cancels.

**Dropper keeps palette effects** preserves company-colour, animation and other explicit mask indices when the source and project palettes match. Ordinary indexed colours become ordinary RGB paint. Disable the option to copy the displayed colour without an effect. Reference sampling reads the original indexed PNG/mask directly, preserving the precise index even if two palette entries have identical RGB colours. If the source uses a different DOS/Windows palette, the dropper copies RGB only and reports that the effect was omitted.

The dropper works for buildings too: the picked colour/effect is copied into the selected part's material controls; use **Apply part changes** or **Paint selected part** to apply it. Sampling alone does not edit the model or add an undo entry. **M / Material** retains the terrain sampler for the original unlit voxel material and cap shape; the dropper samples the rendered pixel, including its lighting or texture.

## Colour modes

| Mode | Export |
|---|---|
| 8bpp | Indexed PNGs in the chosen DOS/Windows palette; index 0 is transparent. |
| RGB / 32bpp | RGBA PNGs, plus a normal-zoom 8bpp fallback required by the generated NML. |
| Both | Indexed and RGBA images at every selected zoom. |

Ordinary palette conversion excludes transparency, company blue, palette-animation indices, unused pink and reserved white. Optional ordered dithering uses only ordinary indices. Explicit palette-effect paint and imported special indices are retained separately and become indexed masks alongside 32bpp images. The 32bpp mask uses OpenTTD's neutral brightness of 128, preserving source-mask intensity separately from palette shade. These effects require appropriate game recolouring/animation context; a mask alone does not define that context.

Texture relighting defaults to **0%**, retaining source shading. Increase it deliberately to blend in the voxel lighting; the tool does not claim to recover unshaded material colours from existing artwork. References and textured output must use the same palette; re-import with another palette when needed.

## Geometry, placement and export

World tile X/Y span 0..16; Z is measured in normal-zoom screen pixels. The fixed projection is `screen_x = 2*(y-x)`, `screen_y = x+y-z`. Raster sampling is calibrated to these flat-tile contracts:

| Zoom | Visible rectangle | X offset | Y offset |
|---|---:|---:|---:|
| 1× | 64×31 | -31 | 0 |
| 2× | 128×63 | -62 | -1 |
| 4× | 256×127 | -124 | -2 |

Offsets come from the cropped image's position relative to the **north tile corner**, never the image centre. Every export includes exact bounds, offsets, file hashes, reference provenance, complete NML, and an editable project. NOCROP keeps the compiler from changing the supplied bounds.

**Ground tile:** uses the selected TTD preset's geometric silhouette. In Custom/reference mode, it clips to the reference alpha silhouette or a flat diamond. External column walls are omitted. Export stops if any pixel in the footprint has no model surface: repair the boundary, choose a matching reference, or use raised-object placement. Select the correct **terrain family base** or manual **base-game sprite ID** (0..4895), climate and slope. Each ground tile in a collection must have a unique target. The tool does not infer terrain meaning from an arbitrary NewGRF's action chains or sprite numbers.

**Raised tile object:** includes visible column sides and generates a buildable, single-tile NewObject with a full 16×16 footprint and geometry-derived height/sorting box. The generated callback permits flat land only. These are decorative objects; a rendered mound does not alter the game's underlying terrain heights.

**Legacy 8bpp ground export:** emits normal-zoom indexed images, GRF version 7 NFO and, when requested, a container-version-1 GRF. This is for the TTD/TTDPatch NewGRF pipeline; unpatched original TTD does not load NewGRFs. Legacy gameplay compatibility still requires testing with the intended TTDPatch version.

**Include compiled test GRF:** compiles modern exports with NML, legacy exports with GRFCodec. Compilation errors stop the export. The generated GRFID depends on the project content, suitable for test builds rather than savegame-stable published releases. For a released mod, choose and maintain its GRFID/version in the generated source.

## Validation

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe tools/export_demo.py --build
```

Tests cover all cap shapes/rotations, all 19 native slope surfaces and joins at each grid size, exact sprite bounds at all zooms, flat/ramp patch coverage without gaps or overlap, origin preservation, surface picking, texture reprojection, reserved palette indices, company masks, malformed project data, and compiler-to-GRFCodec round trips of image pixels, masks, sizes and offsets. Compiler/decoder integration tests skip explicitly when those tools are unavailable. See VALIDATION.md for the executed checks.

The complete picture/dropper/building browser regression starts and stops its own local test server (port 7866 by default). Install the optional test dependency and Chromium first:

```sh
npm install --no-save --package-lock=false playwright
npx playwright install chromium
```

On Windows, run from the repository root:

```powershell
$env:WORKSHOP_PYTHON = (Resolve-Path .venv/Scripts/python.exe).Path
node tests/buildings_ui.cjs
```

On Linux/macOS:

```sh
WORKSHOP_PYTHON="$PWD/.venv/bin/python" node tests/buildings_ui.cjs
```

Set `WORKSHOP_BROWSER` to an installed Chromium-family browser executable to use it instead of Playwright's browser. `WORKSHOP_URL` selects the test URL/port; `WORKSHOP_REUSE_SERVER=1` uses an already-running backend. These checks write only to the ignored `.work/` directory.

Optional browser smoke tests use Playwright (`node tests/ui.cjs`) with the app running. Set `WORKSHOP_BROWSER` to a Chromium-family browser when Playwright browsers are not installed, and `WORKSHOP_TEST_GRF` to a GRF for the import exercise. Screenshots and the downloaded export go under `.work/`.

Compilation and pixel checks do not establish in-game art acceptance. Before publishing, test placement, slopes, transparency, company/animated colours, overlaps with vehicles/buildings, and all target zoom levels in the intended game/base set. Lighting defaults follow TTD's lower-right sun convention; matching a particular graphics set still needs visual review.

## Scope and attribution

Terrain mode models solid voxel columns with shaped caps. Building mode assembles overlapping parts, including raised floors and overhangs within the lot. Arbitrary mesh/VOX import, a freely rotating camera, and automatic 3D reconstruction from 2D art are not implemented. Shadows and ambient occlusion are baked from the current model; neighbouring in-game geometry does not cast shadows into the render.

The application is GPL-2.0-only; upstream components retain their own notices. See ../LICENSE, ../LICENSE_NOTICE.md and ../THIRD_PARTY.md. No TTD/OpenGFX artwork or third-party game binaries are bundled. Reference artwork remains subject to its original licence.
