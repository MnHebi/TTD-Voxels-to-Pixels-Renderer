# SPDX-License-Identifier: GPL-2.0-only
"""Record a local decoder path without modifying shared environment settings."""
import argparse
import json
from pathlib import Path

parser=argparse.ArgumentParser()
parser.add_argument("--grfcodec",required=True,type=Path)
args=parser.parse_args()
if not args.grfcodec.is_file():
    parser.error("The GRFCodec executable does not exist")
root=Path(__file__).resolve().parent.parent
(root/"local.json").write_text(json.dumps({"grfcodec":str(args.grfcodec.resolve())},indent=2)+"\n")
print("GRFCodec configured for this workshop.")
