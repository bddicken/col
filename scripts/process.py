#!/usr/bin/env python3
"""Make the app files in data/processed/ from the source files in data/raw/.

Usage:
    python scripts/process.py                   Do all the steps.
    python scripts/process.py states counties   Do only the given steps.

The steps are states, counties, cities, and by_state. The by_state step uses
the output of the other three steps. Do the download (scripts/download.py)
before this script.
"""

import shutil
import sys
import time

import build_cities
import build_counties
import build_state_files
import build_states
from common import PROCESSED, RAW

STEPS = {
    "states": build_states.build,
    "counties": build_counties.build,
    "cities": build_cities.build,
    "by_state": build_state_files.build,  # needs the three above
}


def copy_geometry():
    """Ship the us-atlas TopoJSON next to the data so the app has one folder to load."""
    out = PROCESSED / "geo"
    out.mkdir(parents=True, exist_ok=True)
    for path in (RAW / "geo").glob("*-10m.json"):
        shutil.copy2(path, out / path.name)
    print(f"[geo] copied us-atlas TopoJSON to {out.relative_to(PROCESSED.parent.parent)}")


def main():
    steps = sys.argv[1:] or list(STEPS)
    for name in steps:
        t0 = time.time()
        STEPS[name]()
        print(f"  ({time.time() - t0:.0f}s)")
    copy_geometry()


if __name__ == "__main__":
    main()
