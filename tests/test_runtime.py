# SPDX-License-Identifier: GPL-2.0-only
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from voxelterrain import runtime


class RuntimeTests(unittest.TestCase):
    def test_source_and_user_data_locations(self):
        home=Path(tempfile.gettempdir())/"ttd-test-home"
        self.assertEqual(runtime.data_directory(frozen=False,environ={},home=home),runtime.RESOURCE_ROOT/".work")
        self.assertEqual(runtime.data_directory("win32",True,{},home),home/"AppData/Local/TTDVoxelsToPixels")
        self.assertEqual(runtime.data_directory("darwin",True,{},home),home/"Library/Application Support/TTDVoxelsToPixels")
        self.assertEqual(runtime.data_directory("linux",True,{},home),home/".local/share/TTDVoxelsToPixels")
        custom=home/"custom"
        self.assertEqual(runtime.data_directory("linux",True,{"XDG_DATA_HOME":str(custom)},home),custom/"TTDVoxelsToPixels")
        self.assertEqual(runtime.data_directory("linux",True,{"XDG_DATA_HOME":"relative"},home),home/".local/share/TTDVoxelsToPixels")
        self.assertEqual(runtime.data_directory(frozen=True,environ={"TTD_VOXELS_DATA_DIR":str(custom)},home=home),custom.resolve())

    def test_external_library_paths_are_restored_without_mutating_parent(self):
        with tempfile.TemporaryDirectory() as folder:
            bundle=Path(folder)/"bundle";system=Path(folder)/"system"
            with patch.object(runtime,"FROZEN",True),patch.object(runtime,"RESOURCE_ROOT",bundle),patch.dict(os.environ,{
                "LD_LIBRARY_PATH":str(bundle),"LD_LIBRARY_PATH_ORIG":str(system),
                "PATH":os.pathsep.join([str(bundle),str(bundle/"tools"),str(system)]),"DYLD_LIBRARY_PATH":str(bundle)}):
                env=runtime.external_environment()
                self.assertEqual(env["LD_LIBRARY_PATH"],str(system))
                self.assertEqual(env["PATH"],str(system))
                self.assertEqual(env["DYLD_LIBRARY_PATH"],"")
                self.assertEqual(os.environ["LD_LIBRARY_PATH"],str(bundle))

    def test_entry_point_help_version_and_port_errors_do_not_start_server(self):
        app=runtime.RESOURCE_ROOT/"app.py"
        result=subprocess.run([sys.executable,str(app),"--version"],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0);self.assertIn("TTD Voxels to Pixels",result.stdout)
        result=subprocess.run([sys.executable,str(app),"--port","65536"],capture_output=True,text=True,timeout=10)
        self.assertNotEqual(result.returncode,0);self.assertIn("Port must be",result.stderr)

    def test_compiler_worker_entrypoint(self):
        # Same entrypoint is used by frozen NML workers; source fallback supplies its PYTHONPATH.
        from voxelterrain.export import compiler_available
        if not compiler_available():self.skipTest("NML unavailable")
        env=os.environ.copy()
        env["PYTHONPATH"]=os.pathsep.join([str(runtime.DATA_ROOT/"compiler"),env.get("PYTHONPATH","")])
        result=subprocess.run([sys.executable,str(runtime.RESOURCE_ROOT/"app.py"),"--compile-nml","--version"],
                              capture_output=True,text=True,env=env,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr);self.assertIn("nml",result.stdout.lower())


if __name__=="__main__":unittest.main()
