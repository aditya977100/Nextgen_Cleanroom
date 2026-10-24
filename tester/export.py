"""Copy a results file into the dashboard folder."""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def export_run(src, mode):
    dst = ROOT / "dashboard" / "data" / f"{mode}.json"
    shutil.copyfile(src, dst)
    return dst
