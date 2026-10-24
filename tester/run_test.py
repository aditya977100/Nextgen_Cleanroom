"""The invigilator. Examples:

  python -m tester.run_test                              # simulation engine, all three modes, export to dashboard
  python -m tester.run_test --engine sim --mode slip
  python -m tester.run_test --engine docker --mode cleanroom   (after Phase 3)
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tester.export import export_run  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--engine", choices=["sim", "docker"], default="sim")
    p.add_argument("--mode", choices=["naive", "cleanroom", "slip", "all"], default="all")
    p.add_argument("--keep", action="store_true", help="docker engine: leave containers running")
    p.add_argument("--no-export", action="store_true", help="do not copy results into dashboard/data/")
    a = p.parse_args()

    if a.engine == "sim":
        from tester.engine_sim import run
    else:
        from tester.engine_docker import run as _run
        run = lambda m: _run(m, keep=a.keep)  # noqa: E731

    modes = ["naive", "cleanroom", "slip"] if a.mode == "all" else [a.mode]
    (ROOT / "results").mkdir(exist_ok=True)
    for m in modes:
        print(f"[{m}] running the {a.engine} engine...", flush=True)
        res = run(m)
        out = ROOT / "results" / f"{a.engine}-{m}.json"
        out.write_text(json.dumps(res, indent=1))
        if not a.no_export:
            export_run(out, m)
        bad = [f["id"] for f in res["findings"] if f["status"] == "TAINTED"]
        print(f"[{m}] {res['certificate']}  tainted={bad or 'none'}  "
              f"mole={res['mole']['landed']}/{res['mole']['tried']}  -> {out.name}", flush=True)


if __name__ == "__main__":
    main()
