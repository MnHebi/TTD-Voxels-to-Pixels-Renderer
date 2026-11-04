# SPDX-License-Identifier: GPL-2.0-only
"""Run: python app.py [--no-browser] [--port 7865]."""
import argparse
import json
import os
from pathlib import Path
import sys
import threading


def main():
    parser=argparse.ArgumentParser(description="OpenTTD Voxel Terrain Workshop (local only)")
    parser.add_argument("--port",type=int,default=7865)
    parser.add_argument("--no-browser",action="store_true")
    parser.add_argument("--data-dir",type=Path,help="Writable data/config/export directory")
    parser.add_argument("--grfcodec",type=Path,help="Save the path to an external GRFCodec executable")
    from voxelterrain import __version__
    parser.add_argument("--version",action="version",version=f"TTD Voxels to Pixels Renderer {__version__}")
    parser.add_argument("--compile-nml",nargs=argparse.REMAINDER,help=argparse.SUPPRESS)
    args=parser.parse_args()
    if args.compile_nml is not None:
        from nml.main import main as nml_main
        return nml_main(args.compile_nml)
    if not 0<=args.port<=65535:parser.error("Port must be 0..65535")
    if args.data_dir:os.environ["TTD_VOXELS_DATA_DIR"]=str(args.data_dir.expanduser().resolve())
    from voxelterrain.runtime import DATA_ROOT, CONFIG_PATH, open_browser
    DATA_ROOT.mkdir(parents=True,exist_ok=True)
    if args.grfcodec:
        if not args.grfcodec.is_file():parser.error("GRFCodec executable does not exist")
        CONFIG_PATH.parent.mkdir(parents=True,exist_ok=True)
        CONFIG_PATH.write_text(json.dumps({"grfcodec":str(args.grfcodec.resolve())},indent=2)+"\n",encoding="utf-8")
    from voxelterrain.server import Workshop
    try:server=Workshop(("127.0.0.1",args.port))
    except OSError as exc:
        parser.exit(1,f"Cannot start workshop on port {args.port}: {exc}\nClose the other instance or choose --port 7866.\n")
    url=f"http://127.0.0.1:{server.server_port}/"
    print(f"Voxel Terrain Workshop: {url}\nVersion: {__version__}\nData directory: {DATA_ROOT}\nKeep this window open. Press Ctrl+C to stop.",flush=True)
    if not args.no_browser:
        timer=threading.Timer(.5,lambda:open_browser(url));timer.daemon=True;timer.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__=="__main__":
    sys.exit(main())
