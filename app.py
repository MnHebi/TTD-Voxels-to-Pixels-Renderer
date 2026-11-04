# SPDX-License-Identifier: GPL-2.0-only
"""Run: python app.py [--no-browser] [--port 7865]."""
import argparse
import threading
import webbrowser

from voxelterrain.server import Workshop


def main():
    parser=argparse.ArgumentParser(description="OpenTTD Voxel Terrain Workshop (local only)")
    parser.add_argument("--port",type=int,default=7865)
    parser.add_argument("--no-browser",action="store_true")
    args=parser.parse_args()
    server=Workshop(("127.0.0.1",args.port))
    url=f"http://127.0.0.1:{server.server_port}/"
    print(f"Voxel Terrain Workshop: {url}\nPress Ctrl+C to stop.",flush=True)
    if not args.no_browser:
        threading.Timer(.5,lambda:webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__=="__main__":
    main()
