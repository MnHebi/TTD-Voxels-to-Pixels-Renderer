# Standalone app packages

The app packages include the local Python runtime, Pillow, NumPy, NML, and a
native GRFCodec built with static PNG/zlib libraries. End users do not need to
install Python or a separate decoder. The editor still opens in their normal
browser; the executable runs its loopback-only backend.

## Install and run

Download the archive matching your operating system and architecture from the
[releases page](https://github.com/MnHebi/TTD-Voxels-to-Pixels-Renderer/releases).
Extract the **complete folder**, preserving its `_internal` directory. Moving
only the executable will not work.

| Package | Start | Support scope |
| --- | --- | --- |
| Windows x64 ZIP | `Start Workshop.cmd` or `TTDVoxelsToPixels.exe` | Windows 10/11 x64; package smoke test plus the existing Windows browser checks. |
| Linux x64 tar.gz | `./start-workshop.sh` or `./TTDVoxelsToPixels` | Built on Ubuntu 22.04; desktop Linux with glibc 2.35+ and a browser. Broader desktop validation is welcome. |
| macOS arm64 tar.gz | `Start Workshop.command` or the executable in Terminal | Experimental Apple Silicon build, targeting macOS 15+. Needs community validation. |
| macOS x64 tar.gz | `Start Workshop.command` or the executable in Terminal | Experimental Intel build, targeting macOS 15+. Needs community validation. |

The console prints the local URL, version and data location. Keep that console
open while using the editor. **Ctrl+C** stops the backend; closing a browser tab
does not stop it. If port 7865 is busy, close the other instance or start with
`--port 7866`. Browser autosave is specific to the browser profile and local URL.

These initial packages are unsigned; the macOS builds are not notarized. Use
your operating system's normal application-approval flow only if you trust the
download. No signing certificate or Apple developer identity is bundled.

## Data and configuration

The installation folder can be read-only. Default writable locations are:

- Windows: `%LOCALAPPDATA%\TTDVoxelsToPixels`
- Linux: `$XDG_DATA_HOME/TTDVoxelsToPixels`, or `~/.local/share/TTDVoxelsToPixels`
- macOS: `~/Library/Application Support/TTDVoxelsToPixels`

Exports, temporary imports and optional `local.json` configuration go there.
The browser continues storing project autosave and screenshot references in its
own local storage/IndexedDB. Use **Save project** to make transferable backups.

Override the data location using `--data-dir PATH` or `TTD_VOXELS_DATA_DIR`. A
portable copy can use a folder of your choice next to the extracted application;
the application never assumes it can write into its bundled resources.

Bundled GRFCodec is discovered automatically. To override it, set `GRFCODEC`,
or start with `--grfcodec /absolute/path/to/grfcodec`. This records the path in
the selected user-data directory. The source checkout retains its existing
`.work/` and root `local.json` behaviour unless a data override is supplied.

## Build from source

Release builds require **Python 3.12**, CMake, and a native C/C++ compiler.
PyInstaller builds are created on the target OS; this is not cross-compilation.
Install `requirements-build.txt` into an isolated environment, then run:

```sh
python tools/build_app.py
```

On a MinGW setup use `--generator Ninja` if needed. The builder downloads pinned
GRFCodec 6.1.0-g4c71c0a (a pinned upstream snapshot without the old Boost dependency), zlib 1.3.1 and libpng 1.6.50 sources by immutable Git revision,
builds their native helper, and packages the editor. It does not bundle locally
decoded GRFs, `local.json`, user projects or the developer's Python installation.
`--without-grfcodec` is available for editor-only development builds; full
release smoke tests deliberately require the decoder.

Outputs are placed under `dist/` with platform/architecture names and SHA-256
sidecars. macOS/Linux use tar.gz to preserve executable bits and the symlinks
required by PyInstaller. Windows uses ZIP. Each folder includes:

- The executable and `_internal` resources/libraries.
- A launcher and `START_HERE.txt`.
- `BUNDLE_MANIFEST.json` with versions and source provenance.
- The application licence and dependency notices under `licenses/`.
- Exact application and NML source archives, plus the pinned native helper and
  PNG/zlib sources, under `sources/`.

The NML compiler uses a dedicated worker mode in the frozen executable; it does
not invoke a system Python interpreter. External user-specified tools and browser
launches receive a cleaned library-search environment.

## Automated and community validation

The **Standalone apps** Actions workflow builds Windows x64, Linux x64, Apple
Silicon macOS and Intel macOS. It runs source tests using the built decoder, then
starts the bundled executable from a separate directory with Python/GRFCodec
removed from its PATH. `tools/smoke_app.py` checks:

- Static UI resources and palette loading.
- Rendering and separate writable user data.
- Compilation through bundled NML, import through bundled GRFCodec, and legacy
  encoding.
- JPEG import and perceptual palette conversion.

The build artifacts include smoke-test JSON evidence. Version tags publish a
**prerelease**, after all four build jobs pass. A successful hosted macOS build
or HTTP smoke test is **not** hands-on Mac validation: browser opening, Finder
launch, OS approval, window behaviour, picture persistence and game rendering
still need reports from Mac users. We do not have local Mac hardware.

When reporting a problem, include OS version, CPU architecture, app version,
console output and which workflow failed. Please test saving/reopening projects,
GRF imports, all colour modes, reference-picture zoom/pan and compiled exports.
Do not attach third-party artwork without permission.
