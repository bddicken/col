#!/usr/bin/env python3
"""Make the app files in data/processed/ from the source files in data/raw/.

Usage:
    python scripts/process.py                   Do all the steps.
    python scripts/process.py states counties   Do only the given steps.

The steps are states, counties, cities, and by_state. The by_state step uses
the output of the other three steps. Do the download (scripts/download.py)
before this script.

The script also copies the files that the app loads to data/processed/web/.
Only this directory is deployed.
"""

import shutil
import sys
import time

import build_cities
import build_counties
import build_state_files
import build_states
from common import PROCESSED, RAW, ROOT

STEPS = {
    "states": build_states.build,
    "counties": build_counties.build,
    "cities": build_cities.build,
    "by_state": build_state_files.build,  # needs the three above
}


# The files that the app loads. Only data/processed/web/ is deployed.
WEB_FILES = ["states.json", "geo/states-albers-10m.json", "geo/counties-albers-10m.json"]


def copy_geometry():
    """Copy the us-atlas TopoJSON next to the processed data."""
    out = PROCESSED / "geo"
    out.mkdir(parents=True, exist_ok=True)
    for path in (RAW / "geo").glob("*-10m.json"):
        shutil.copy2(path, out / path.name)
    print(f"[geo] copied us-atlas TopoJSON to {out.relative_to(ROOT)}")


def assemble_web():
    """Copy the files that the app loads to data/processed/web/.
    The by_state step writes its files to web/by_state/ directly."""
    web = PROCESSED / "web"
    for rel in WEB_FILES:
        (web / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PROCESSED / rel, web / rel)
    size = sum(f.stat().st_size for f in web.rglob("*") if f.is_file())
    print(f"[web] app files in {web.relative_to(ROOT)} ({size / 1e6:.1f} MB)")


def main():
    steps = sys.argv[1:] or list(STEPS)
    for name in steps:
        t0 = time.time()
        STEPS[name]()
        print(f"  ({time.time() - t0:.0f}s)")
    copy_geometry()
    assemble_web()


if __name__ == "__main__":
    main()
