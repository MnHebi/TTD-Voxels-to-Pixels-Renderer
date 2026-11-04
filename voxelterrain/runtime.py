# SPDX-License-Identifier: GPL-2.0-only
"""Immutable application resources, writable user data and frozen-process helpers."""
from contextlib import contextmanager
import os
from pathlib import Path
import subprocess
import sys
import threading
import webbrowser

FROZEN=bool(getattr(sys,"frozen",False))
RESOURCE_ROOT=Path(getattr(sys,"_MEIPASS",Path(__file__).resolve().parent.parent)).resolve()


def data_directory(platform=None, frozen=None, environ=None, home=None):
    platform=platform or sys.platform
    frozen=FROZEN if frozen is None else frozen
    env=os.environ if environ is None else environ
    home=Path.home() if home is None else Path(home)
    if env.get("TTD_VOXELS_DATA_DIR"):
        return Path(env["TTD_VOXELS_DATA_DIR"]).expanduser().resolve()
    if not frozen:return RESOURCE_ROOT/".work"
    if platform=="win32":
        base=Path(env.get("LOCALAPPDATA",home/"AppData/Local"))
    elif platform=="darwin":base=home/"Library/Application Support"
    else:
        configured=Path(env.get("XDG_DATA_HOME",""))
        base=configured if configured.is_absolute() else home/".local/share"
    return base/"TTDVoxelsToPixels"


DATA_ROOT=data_directory()
CONFIG_PATH=DATA_ROOT/"local.json" if FROZEN or os.environ.get("TTD_VOXELS_DATA_DIR") else RESOURCE_ROOT/"local.json"
_external_lock=threading.RLock()


def external_environment():
    env=os.environ.copy()
    if FROZEN:
        for key in ("LD_LIBRARY_PATH","LIBPATH"):
            if key+"_ORIG" in env:env[key]=env[key+"_ORIG"]
            else:env.pop(key,None)
        for key in ("PATH","DYLD_LIBRARY_PATH"):
            if key in env:
                env[key]=os.pathsep.join(p for p in env[key].split(os.pathsep)
                                        if p and not Path(p).resolve().is_relative_to(RESOURCE_ROOT))
    return env


@contextmanager
def external_process_environment():
    """Reset PyInstaller's process-wide Windows DLL search path for external tools."""
    with _external_lock:
        if FROZEN and sys.platform=="win32":
            import ctypes
            ctypes.windll.kernel32.SetDllDirectoryW(None)
        try:yield
        finally:
            if FROZEN and sys.platform=="win32":
                import ctypes
                ctypes.windll.kernel32.SetDllDirectoryW(str(RESOURCE_ROOT))


def run_tool(command, **kwargs):
    bundled=FROZEN and Path(command[0]).resolve().is_relative_to(RESOURCE_ROOT)
    if bundled:return subprocess.run(command,**kwargs)
    with external_process_environment():
        return subprocess.run(command,env=external_environment(),**kwargs)


def open_browser(url):
    # Browser launchers cannot accept an env argument; restore the parent's env afterwards.
    with external_process_environment():
        changed={key:os.environ.get(key) for key in ("LD_LIBRARY_PATH","LIBPATH","PATH","DYLD_LIBRARY_PATH")}
        clean=external_environment()
        try:
            for key in changed:
                if key in clean:os.environ[key]=clean[key]
                else:os.environ.pop(key,None)
            return webbrowser.open(url)
        finally:
            for key,value in changed.items():
                if value is None:os.environ.pop(key,None)
                else:os.environ[key]=value
