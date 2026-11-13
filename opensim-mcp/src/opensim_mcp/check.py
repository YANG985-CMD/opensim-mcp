"""Local smoke check. Run from an installed environment; output is JSON, not MCP."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .core import Settings, environment, inspect_model, read_motion, run_ik


def check_demo(cfg: Settings, examples: Path) -> dict:
    result = run_ik(cfg, str(examples / "slider.osim"), str(examples / "slider.trc"))
    table = read_motion(Path(result["motion_file"]))
    index = table["columns"].index("slider_tx")
    # The supplied marker triplets are translated by 0.1*t metres along X.
    error = max(abs(row[index] - 0.1*row[0]) for row in table["rows"])
    if len(table["rows"]) != 11 or error > 1e-6:
        raise AssertionError(f"Analytic slider validation failed: rows={len(table['rows'])}, error={error}")
    result["demo_validation"] = {"max_absolute_coordinate_error_m": error, "tolerance_m": 1e-6,
                                 "expected_rows": 11, "passed": True}
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--examples", type=Path, required=True)
    parser.add_argument("--run-ik", action="store_true", help="Actually execute OpenSim and save a result.")
    args = parser.parse_args()
    cfg = Settings.from_env()
    examples = args.examples.resolve()
    result = {"environment": environment(cfg), "inspection": inspect_model(cfg, str(examples / "slider.osim"))}
    if args.run_ik:
        result["ik"] = check_demo(cfg, examples)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

