"""Codex stdio entry point. No writes to user source/model directories on startup."""
import os
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parent
scratch = Path(os.environ.get("SWLOCAL_TEMP", r"E:\simulink\_codex_tmp\solidworks_local_runtime"))
scratch.mkdir(parents=True, exist_ok=True)
os.environ["TEMP"] = os.environ["TMP"] = str(scratch)
os.environ["SWLOCAL_TEMP"] = str(scratch)
tempfile.tempdir = str(scratch)
sys.dont_write_bytecode = True
sys.path.insert(0, str(root))
from swlocal.server import main

if __name__ == "__main__":
    main()
