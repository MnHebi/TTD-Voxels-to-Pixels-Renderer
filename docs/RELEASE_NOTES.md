# Standalone browser app preview

This prerelease packages the voxel editor as native Windows x64, Linux x64,
macOS Apple Silicon and macOS Intel applications. The Python runtime, rendering
libraries, NML compiler and GRFCodec are included. The interface remains in your
normal browser.

Extract the **complete application folder**, then run its executable or launcher.
Keep the backend console open while using the editor; Ctrl+C stops it.

Included features: terrain caps and 19 TTD slopes; decorative buildings and town
houses; separate PNG/GRF exports; DOS/Windows palettes; reference-picture gallery;
colour-family matching; dropper; independent picture zoom/pan and saved projects.

The assets include per-platform smoke-test reports and SHA-256 checksums. Package
smoke tests exercise rendering, bundled compilation/decoding, legacy output and
screenshot conversion without Python on the app's PATH. These are automated
checks, not gameplay or artistic approval.

**macOS builds are experimental, unsigned and not notarized. We have no local
Mac hardware; hands-on validation is left to community testers.** Finder launch,
browser opening and day-to-day Mac use need audience feedback even when hosted
build/smoke checks pass. Linux desktop feedback is also welcome.

See [app-package instructions](https://github.com/MnHebi/TTD-Voxels-to-Pixels-Renderer/blob/main/docs/APP_PACKAGES.md)
for start commands, writable data locations, troubleshooting, source code and
validation scope. Original game artwork is not bundled.
