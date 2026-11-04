# Validation record — 4 November 2026

Status: **0.5 Windows package verified by automated checks; READY_FOR_USER_ART_REVIEW**. In-game visual acceptance, town growth and cargo behaviour remain pending. macOS desktop validation requires community testers.

## Standalone packages (0.5)

- **69 Python tests passed**, including four runtime checks covering OS data locations, external-tool environments, command-line validation and the frozen compiler worker entry point.
- The extracted Windows x64 ZIP passed `tools/smoke_app.py` from a separate working directory with Python and GRFCodec removed from the application's PATH. Checks covered bundled static assets/palettes, rendering, NML compilation, GRFCodec import, legacy encoding, JPEG import, perceptual palette conversion and a separate writable data directory. Evidence is emitted as `windows-x64-smoke.json`; the smoke fixture's compiled GRF SHA-256 is `4c3e8575a0dbe4b8cc58029f4c06f0831227755d7760d21d45df1c40ca5c143f`.
- The existing reference-picture, dropper and building browser regressions passed against the frozen Windows backend in headless Brave, including pane zoom/pan/persistence, project save/open and compiled building export. **Zero JavaScript exceptions.**
- The native-build workflow runs source tests and extracted-package smoke checks on Windows, Linux and both Mac architectures. Per-run Actions results and emitted JSON reports establish whether those exact packages passed; merely adding a matrix entry does not establish a successful build.
- [Hosted validation run 41824438098](https://github.com/MnHebi/TTD-Voxels-to-Pixels-Renderer/actions/runs/41824438098) passed for **Windows x64, Linux x64, macOS arm64 and macOS x64** at source commit `7075199`. Each platform passed all 69 source tests and its extracted-package smoke check with an empty tool search path. This establishes automated backend/package behaviour on those hosts, with the manual desktop limitations below.

No local Mac hardware is available. macOS packages are experimental, unsigned and not notarized. Hosted build/HTTP checks do not verify Finder launch, browser opening, OS approval or day-to-day desktop behaviour. Linux desktop integration also needs audience feedback. These package checks add no new gameplay or artistic acceptance evidence.

## Reference-pane zoom controls (0.4 UI update)

The browser regression passed independent −/+ controls above the original and converted panes, zoom-out, drag panning, Fit/reset, clipping at pane boundaries, correct dropper picks after zoom/pan, single-pane control visibility and zoom persistence through project save/open and browser reload. The picture, dropper and building workflows, including compiled export, also passed with zero JavaScript exceptions. The reference-window layout was inspected with one pane enlarged and the other fitted. This is a frontend-only change; the 65-test backend result below is from the preceding palette/window implementation.

## Screenshot references and perceptual palette matching (0.4)

- **65 Python tests passed in 54.975 seconds**, with no skips, including all prior GRF compilation/decoding, terrain, building and mask checks, four dropper checks, and ten new image/palette checks. The full suite ran outside the sandbox so GRFCodec could execute.
- Import tests cover PNG/BMP/lossless WebP pixel preservation, JPEG, the 1600-pixel reference-copy limit, alpha, EXIF rotation, sRGB ICC conversion, gallery limits, malformed uploads, and canonical indexed PNG output.
- Colour tests check published OKLab primary values, explicit muted-green fixtures that RGB distance maps toward brown/yellow, neutral ramps staying neutral, dithering improving mean perceptual tone on a grey patch, exact ordinary-palette colours, both DOS and Windows palettes, transparency, effect tags, deterministic results and the large-photo histogram branch. Old projects retain Nearest RGB; invalid matching options fail validation.
- The isolated browser picture-window test passed multi-image import, previous/next and keyboard cycling, image selection, original/nearest/colour-family modes, DOS/Windows choice, comparison, dropper samples from both panels, indexed PNG download, moving/resizing, project save/reopen, local IndexedDB persistence across reload and hide/show. Screenshot-reference operations leave the voxel model unchanged. The window was visually inspected using a synthetic reference fixture; this is not an in-game art review.
- The complete dropper and building-editor browser regressions also passed after the picture checks, including reference thumbnails, model undo, project save/open and compiled house export. Zero JavaScript exceptions. The dropper browser fixture now uses a deterministic authored PNG instead of relying on browser canvas-to-PNG colour encoding.
- A 30×30×30 synthetic RGB sweep, restricted to chromatic samples, measured mean absolute hue error of about 17.15 degrees for Nearest RGB versus 9.51 degrees for colour-family matching. This is fixture-specific evidence, not a guarantee for arbitrary game screenshots. A 1280×720 random-image conversion with dithering took about 1.61 seconds locally after bounding the histogram work.

Screenshot references are normalised copies; original files are unchanged. The conversion preserves palette membership and aims to protect hue and neutrality, with a possible lightness/chroma tradeoff. It does not guarantee exact source colour balance outside the palette gamut. Earlier engine-loading evidence below remains evidence for those earlier GRFs; no new gameplay or art approval is implied by picture-window validation.

## Sprite dropper (0.3.1)

- Four focused Python tests passed for exact source RGB/alpha/coordinates, missing/out-of-range inputs, duplicate-RGB indexed entries retaining distinct indices, 32bpp masks, and Windows animation indices.
- The isolated browser test passed pixel picking from the rendered RGB sprite, indexed output, Compare reference, a 50% reference overlay, any repeated tile, and a letterboxed library thumbnail. It verifies transparent pixels leave the brush unchanged; sampling does not add an undo entry; special indices absent from the original dropdown remain selectable; effect preservation can be disabled; Esc cancels; a library sample leaves the current reference unchanged; and sampled colours can be applied to a building part.
- The complete existing building-editor browser workflow also passed after those checks, including undo/redo, project save/reopen and compiled house export, with zero JavaScript exceptions.
- Sampling uses source pixels and exact indexed data, not screenshot RGB or nearest-palette guesses. The earlier terrain, compiler and engine-load evidence below belongs to the preceding releases; the dropper change does not change geometry or GRF layout generation.

## Building support (0.3)

- **51 Python tests passed in 50.079 seconds**, with no skipped tests: the previous 39 plus 12 building/house checks. The suite ran outside the sandbox because Windows blocked GRFCodec inside it with WinError 623 (DLL relocation). The unrestricted run passed all original decode/legacy checks as well.
- Tests cover old-project migration, five presets, validation, four roof/box types, both roof axes, all four views, unit normals, triangle-interior heights, volume occupancy, empty space below elevated parts, exact construction cut surfaces, rectangular-lot rotation, transparent courtyards, and the 128-pixel height limit.
- Independent tile fragments reassemble **exactly** at all three zooms and four orientations, including RGB, indexed pixels, company-colour masks and alpha, with zero missing or overlapping visible pixels. Texture projection reproduces the input render with zero uncovered pixels in the self-projection fixture.
- All four lot sizes compile for both NewObjects and FEAT_HOUSES, including a selected odd orientation. Generated house substitutes match their footprint; town properties, default-house preservation, and preconstruction object slope checks are asserted.
- The combined two-tile object/house fixture compiles all four views and construction stages at every zoom: **264 sprite images**. GRFCodec decoding preserves every tested pixel, palette index, size, zoom and signed offset exactly. Masked 32bpp output is included.
- The isolated headless-Brave building-editor test passed: placement switch, part edits, palette tags, undo/redo, duplication, deletion, addition, roof changes, rotation, construction preview, 2×2 preset, house population, project save/reopen and compiled house export. **Zero JavaScript exceptions.** The test starts and cleans up its own backend; its waits include asynchronous building validation.
- The example pack `exports/buildings.zip` contains **1,056 separate sprite PNGs** (plus masks where needed), four placeable building objects and sixteen house orientations. The showcase is self-authored geometry and materials, without imported artwork. Its review board was inspected for coherent roofs, walls, rotations and bounds.
- An isolated **OpenTTD 16.0-beta5** null-driver session loaded the exact example GRF, started a game and saved `buildings_validation.sav`. GRF SHA-256: `7dbc1087303cdbb363ea5eded075f5a57136674068ec8dcd1c4ecb3d1a02d226`; gamelog GRFID `5654FAA9`, engine checksum `D207CF3E35786DF1A6EB35991FBC8B8A`. Evidence: `.work/runtime/buildings-console.log` and `buildings-load.json`.

The engine run exercises loading, game creation and saving. It does **not** exercise building placement, generated town-house growth, passenger/mail acceptance or production, construction timing, visual sorting or art approval. Buildings use conservative per-tile 16×16 sorting boxes with geometry-derived height; they do not claim tight individual-part sorting. Construction stages are generated height-progress models, without automatic scaffolding. The first release supports flat lots up to 2×2, not industries, stations or legacy building gameplay.

## Shape support (0.2)

- **39 Python tests passed**: the original 26 plus 13 shape/migration/terrain/export checks.
- Eight cap types and all four rotations were checked against triangle-interior surface heights and upward face normals. Ridge and valley hinge diagonals are independently distinguished.
- All 19 TTD profiles match their continuous terrain height functions at 8×8, 16×16 and 32×32 grids, with matching cell-boundary heights. The steep corner bit meanings have explicit expected-height checks.
- Every native slope has the expected sprite size and signed offset at 1×, 2× and 4×. A 3×3 elevated ramp patch has **zero pixel gaps and zero overlaps** at every zoom. Nonrepeatable edge profiles are flagged.
- The complete family compiles, then decodes through GRFCodec with exact exported pixels, sizes and offsets for all **114 individual images**. Shape-cap rise is included in object sorting boxes and NML height.
- The browser shape check passed: all eight shape controls, rotation/brush editing, native preset selection, exact grid resizing, edge-status labels, project save/reopen, and compiled export; **zero JavaScript exceptions**. A final check also exercised the preview's sprite-resolution compositing fix.
- `exports/ttd-slopes.zip` replaces the standard grass family, sprites 3981–3999. `exports/ttd-slope-showcase.png` shows the self-authored rendered results.
- An isolated OpenTTD 16.0-beta5 null-driver session loaded this exact family, created a game and saved `slopes_validation.sav`. The GRF SHA-256 is `23fea8b0eba3fea0b8ac2e70d60e0662ad369411bce92d75107942de4c63d4ea`; gamelog ID `5654A295`, checksum `68E93D00283119F58137A99AC7EEFF43`. Evidence: `.work/runtime/slopes-console.log` and `slopes-load.json`.

Native geometry uses continuous planes. Its normal-zoom bounds match all 19 sampled OpenGFX grass templates; their hand-drawn alpha edges differ by 0–16 pixels per tile. This is not a claim of pixel-identical legacy artwork. Null-driver loading does not establish visual placement, palette animation or artistic acceptance; review in-game before publishing.

## Original import/colour checks (also passing in 0.2)

- **26 Python regression tests passed**, including NML-to-GRFCodec comparisons of every generated image pixel, palette mask, width/height and signed offset in representative DOS/Windows, ground/object, 8bpp/32bpp/both exports. Legacy container-v1 compilation and decoding also passed.
- Both bundled palette tables match NML 0.9.0's canonical palette bytes exactly.
- Flat raster coverage matches the documented 1×/2×/4× geometry. A 3×3 grid has **zero overlapping pixels and zero holes** at every supported zoom. Ground exports with incomplete footprints are rejected.
- Browser smoke test passed using isolated headless Brave: sculpting/undo, colour modes, tiling, GRF import, source selection, surface texturing, reference PNG export, project save/reopen, compiled sprite download and compact layout. **Zero JavaScript exceptions.**
- The final UI download contains separate indexed PNGs and a compiled `workshop.grf`. The selected-reference download contains a separate 64×31 image at offset (-31, 0). Saved project JSON includes the reference pixels.

## Real-file import and reprojection

These files were read from the local machine for testing; their artwork is not part of the application or demo.

| Input | Container | Image variants decoded | Reference | Opaque RGB differences | Alpha differences | Bounds |
|---|---:|---:|---:|---:|---:|---|
| `ogfx1_base.grf` | 2 | 4,855 | 3981 | 0 | 0 | exact |
| `trg1r.grf` | 1 | 4,758 | 3981 | 0 | 0 | exact |

The reprojection check uses a flat model, the imported origin and zero texture relighting. Source hashes and detailed results are retained in `.work/verify-opengfx.json` and `.work/verify-ttd.json`.

## Engine load check

An isolated **OpenTTD 16.0-beta5** session using the null video driver loaded generated modern ground and object GRFs, started a new game, and successfully saved a map. Its gamelog lists both GRFs with matching checksums:

- Ground GRFID: `5654F5CD`; checksum `2DC4AC63088CD3F6DDD5A6DF56C5EF62`.
- Object GRFID: `5654E7F4`; checksum `29B9D881E20296DD08CDBEAEF34E4064`.

Evidence is in `.work/runtime/runtime_console.log` and `.work/runtime/save/validation.sav.sav`. The check used a separate configuration and assets under `.work/runtime/`; it did not change the installed game's settings or files.

The null driver does not render. This check establishes engine loading and game creation, **not** visual placement, sorting, shadows, palette animation or artistic acceptance. Those need an interactive game review. Legacy TTDPatch gameplay has not been run.

## Review artifacts

- `exports/demo.zip`: five self-authored flat/sloped decorative terrain objects, 30 separate PNG sprites across both colour modes and three zooms, plus source, metadata and a compiled test GRF.
- `.work/workshop-desktop.png`: initial editor view.
- `.work/workshop-tiling.png`: repeated-tile preview.
- `.work/workshop-reference.png`: imported reference and textured voxel comparison.
- `.work/workshop-compact.png`: compact-width layout.

Demo slopes are decorative NewObjects on flat land. They do not change actual game terrain height. Arbitrary sloped landscape replacement sets are not automatically inferred from GRF sprite numbers.
