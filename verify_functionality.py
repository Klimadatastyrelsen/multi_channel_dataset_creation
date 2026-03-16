#!/usr/bin/env python3
"""
Run verification steps from README "## Verify that everything works".
Output is written to verification.log (or path given as first argument).
Exit code 0 on success, non-zero on failure.
"""
import os
import subprocess
import sys
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parent / "verification.log"
if len(sys.argv) > 1:
    LOG_PATH = Path(sys.argv[1])

def run(cmd, cwd=None, env=None, timeout=600):
    """Run command, return (stdout+stderr, returncode)."""
    p = subprocess.run(
        cmd,
        shell=True,
        cwd=cwd or Path(__file__).resolve().parent,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env if env is not None else os.environ,
    )
    out = (p.stdout or "") + (p.stderr or "")
    return out, p.returncode

def main():
    lines = []
    repo_root = Path(__file__).resolve().parent

    # Clear log so this run is the only content (check_logs reads this file)
    with open(LOG_PATH, "w"):
        pass

    env_geotiff = {**os.environ, "GTIFF_SRS_SOURCE": "EPSG"}

    lines.append("=== create_dataset.py (example config) ===")
    out, ret = run(
        f"{sys.executable} src/multi_channel_dataset_creation/create_dataset.py --dataset_config configs/create_dataset_example_dataset.ini",
        cwd=repo_root,
        env=env_geotiff,
    )
    lines.append(out)
    lines.append(f"Exit code: {ret}\n")
    if ret != 0:
        with open(LOG_PATH, "w") as f:
            f.write("\n".join(lines))
        return ret

    with open(LOG_PATH, "w") as f:
        f.write("\n".join(lines))
    return 0

if __name__ == "__main__":
    sys.exit(main())
