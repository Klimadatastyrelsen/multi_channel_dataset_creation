#!/usr/bin/env python3
"""
Run verification steps from README "## Verify that everything works".
Output is written to verification.log (or path given as first argument).
Exit code 0 on success, non-zero on failure.
"""
import os
import sys
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parent / "verification.log"
if len(sys.argv) > 1:
    LOG_PATH = Path(sys.argv[1])

ORCH = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ORCH))
from verify_subprocess_streaming import log_message, log_section, stream_run  # noqa: E402

TIMEOUT_DEFAULT = int(os.environ.get("VERIFY_TIMEOUT", "3600"))


def main():
    repo_root = Path(__file__).resolve().parent

    with open(LOG_PATH, "w", encoding="utf-8"):
        pass

    env_geotiff = {**os.environ, "GTIFF_SRS_SOURCE": "EPSG", "PYTHONUNBUFFERED": "1"}

    log_section(LOG_PATH, "=== create_dataset.py (example config) ===")
    ret = stream_run(
        f"{sys.executable} src/multi_channel_dataset_creation/create_dataset.py --dataset_config configs/create_dataset_example_dataset.ini",
        LOG_PATH,
        cwd=repo_root,
        env=env_geotiff,
        timeout=TIMEOUT_DEFAULT,
    )
    log_message(LOG_PATH, f"Exit code: {ret}")
    return ret


if __name__ == "__main__":
    sys.exit(main())
