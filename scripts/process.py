#!/usr/bin/env python3
"""Turn data/raw/ into app-ready files in data/processed/.

Usage:
    python scripts/process.py                  # states, counties, cities
    python scripts/process.py states cities    # a subset (by_state reads their output)
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
