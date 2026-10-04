#!/usr/bin/env python3
"""Download the source data to data/raw/. Each source has its own directory.

Usage:
    python scripts/download.py                     Download all the sources.
    python scripts/download.py --only zillow,fhfa  Download only the given sources.
    python scripts/download.py --force             Download all the files again.
    python scripts/download.py --large             Also download the Zillow ZIP-code files.

The script does not download a file again if the file is already in data/raw/.
If the output shows FAIL lines, run the script again.

Census history: Set CENSUS_API_KEY to a Census API key. The script then also
downloads ACS data from 2005 (states) and 2009 (counties and cities), and the
2000 census data. Without a key, the ACS data starts in 2021.
Request a key at https://api.census.gov/data/key_signup.html.

For the sources and their terms of use, refer to DATA_SOURCES.md.
"""

import argparse
import json
import os
import sys
import time
import zipfile

import requests

from common import ACS_VARS, RAW, STATES, ZHVI_FILE, ZORI_FILE

# huduser.gov serves an HTML challenge page unless the client looks like a browser,
# while FRED stalls on browser user agents, so the UA is chosen per host.
BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
BROWSER_UA_HOSTS = ("www.huduser.gov",)
session = requests.Session()

ZILLOW = "https://files.zillowstatic.com/research/public_csvs"
CENSUS_WWW2 = "https://www2.census.gov"
GAZ = f"{CENSUS_WWW2}/geo/docs/maps-data/data/gazetteer/2025_Gazetteer"
COH = f"{CENSUS_WWW2}/programs-surveys/decennial/tables/time-series"
US_ATLAS = "https://cdn.jsdelivr.net/npm/us-atlas@3"
ACS_SF_YEARS = [2021, 2022, 2023, 2024]  # keyless table-based summary files start in 2021


def static_files(large):
    """(source, filename, url) for every plain file download."""
    files = []
    zhvi_geos = ["State", "Metro", "County", "City"] + (["Zip"] if large else [])
    for geo in zhvi_geos:
        name = ZHVI_FILE.format(geo=geo)
        files.append(("zillow", name, f"{ZILLOW}/zhvi/{name}"))
    for geo in ["Metro", "County", "City"] + (["Zip"] if large else []):
        name = ZORI_FILE.format(geo=geo)
        files.append(("zillow", name, f"{ZILLOW}/zori/{name}"))

    files += [
        ("fhfa", "hpi_master.csv", "https://www.fhfa.gov/hpi/download/monthly/hpi_master.csv"),
        ("fhfa", "hpi_at_county.xlsx", "https://www.fhfa.gov/hpi/download/annual/hpi_at_county.xlsx"),

        ("census", "coh_values_unadj.txt", f"{COH}/coh-values/values-unadj.txt"),
        ("census", "coh_values_adj.txt", f"{COH}/coh-values/values-adj.txt"),
        ("census", "coh_grossrents_unadj.txt", f"{COH}/coh-grossrents/grossrents-unadj.txt"),
        ("census", "coh_grossrents_adj.txt", f"{COH}/coh-grossrents/grossrents-adj.txt"),

        ("bea", "SARPP.zip", "https://apps.bea.gov/regional/zip/SARPP.zip"),
        ("bea", "MARPP.zip", "https://apps.bea.gov/regional/zip/MARPP.zip"),

        ("hud", "FMR_All_1983_2027.csv", "https://www.huduser.gov/portal/datasets/FMR/FMR_All_1983_2027.csv"),

        ("fred", "CPIAUCSL.csv", "https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCSL"),
        ("fred", "MEHOINUSA646N.csv", "https://fred.stlouisfed.org/graph/fredgraph.csv?id=MEHOINUSA646N"),
    ]
    # State median household income (CPS, nominal $), 1984+
    for abbr, _ in STATES.values():
        sid = f"MEHOINUS{abbr}A646N"
        files.append(("fred", f"{sid}.csv", f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"))

    for layer in ["place", "cousubs", "counties", "cbsa", "state"]:
        name = f"2025_Gaz_{layer}_national.zip"
        files.append(("geo", name, f"{GAZ}/{name}"))
    for name in ["states-10m.json", "counties-10m.json", "nation-10m.json",
                 "states-albers-10m.json", "counties-albers-10m.json", "nation-albers-10m.json"]:
        files.append(("geo", name, f"{US_ATLAS}/{name}"))
    return files


# ---------------------------------------------------------------- helpers

def fetch(url, dest, force=False, filter_lines=None):
    """Stream `url` to `dest` atomically. `filter_lines(line) -> bool` keeps
    only matching lines (header always kept)."""
    if dest.exists() and dest.stat().st_size > 0 and not force:
        print(f"  skip  {dest.relative_to(RAW)} (exists)")
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(1, 4):
        try:
            t0 = time.time()
            headers = {"User-Agent": BROWSER_UA} if url.split("/")[2] in BROWSER_UA_HOSTS else {}
            with session.get(url, stream=True, timeout=120, headers=headers) as r:
                r.raise_for_status()
                ctype = r.headers.get("content-type", "")
                if "text/html" in ctype and not url.endswith(".html"):
                    raise RuntimeError(f"got HTML instead of data ({ctype})")
                with open(tmp, "wb") as f:
                    if filter_lines:
                        lines = r.iter_lines(decode_unicode=False)
                        f.write(next(lines) + b"\n")
                        for line in lines:
                            if filter_lines(line):
                                f.write(line + b"\n")
                    else:
                        for chunk in r.iter_content(1 << 20):
                            f.write(chunk)
            tmp.replace(dest)
            size = dest.stat().st_size / 1e6
            print(f"  ok    {dest.relative_to(RAW)} ({size:.1f} MB, {time.time() - t0:.0f}s)")
            return True
        except Exception as e:  # noqa: BLE001 - report and retry any failure
            print(f"  retry {dest.relative_to(RAW)} attempt {attempt}: {e}")
            time.sleep(2 * attempt)
    tmp.unlink(missing_ok=True)
    print(f"  FAIL  {url}")
    return False


def unzip(path):
    out = path.parent / path.stem
    if out.exists():
        return
    with zipfile.ZipFile(path) as z:
        z.extractall(out)


# Summary levels we keep from the (large) ACS summary files.
ACS_KEEP = (b"0100000US", b"0400000US", b"0500000US", b"1600000US")


def download_acs_summary_files(force):
    ok = True
    for year in ACS_SF_YEARS:
        for survey, folder in [("acs1", "1YRData"), ("acs5", "5YRData")]:
            for table in ACS_VARS:
                t = table.lower()
                url = (f"{CENSUS_WWW2}/programs-surveys/acs/summary_file/{year}/table-based-SF/"
                       f"data/{folder}/acsdt{survey[-1]}y{year}-{t}.dat")
                dest = RAW / "census" / "acs" / "sf" / f"{survey}_{year}_{t}.dat"
                ok &= fetch(url, dest, force, filter_lines=lambda l: l.startswith(ACS_KEEP))
    return ok


def census_api(dataset, get, geo_for, geo_in=None):
    params = {"get": ",".join(get), "for": geo_for, "key": os.environ["CENSUS_API_KEY"]}
    if geo_in:
        params["in"] = geo_in
    r = session.get(f"https://api.census.gov/data/{dataset}", params=params, timeout=120,
                    allow_redirects=False)
    if r.headers.get("X-DataWebAPI-KeyError"):
        raise RuntimeError("Census API rejected the key: missing or invalid CENSUS_API_KEY")
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
    return r.json()


def census_api_places(dataset, get):
    """All places nationally; older vintages reject `in=state:*`, so fall back per state."""
    try:
        return census_api(dataset, get, "place:*", "state:*")
    except RuntimeError:
        rows = None
        for fips in STATES:
            part = census_api(dataset, get, "place:*", f"state:{fips}")
            rows = part if rows is None else rows + part[1:]
        return rows


def download_census_api(force):
    """ACS 1-year (states) 2005+ and 5-year (states/counties/places) 2009+, plus 2000 SF3."""
    get = ["NAME"] + [f"{t}_001E" for t in ACS_VARS]
    jobs = []
    for year in range(2005, 2025):
        if year != 2020:  # standard 2020 1-year estimates were never released
            jobs.append((f"acs1_{year}_state", f"{year}/acs/acs1", "state:*"))
            jobs.append((f"acs1_{year}_us", f"{year}/acs/acs1", "us:1"))
    for year in range(2009, 2025):
        jobs.append((f"acs5_{year}_state", f"{year}/acs/acs5", "state:*"))
        jobs.append((f"acs5_{year}_county", f"{year}/acs/acs5", "county:*"))
        jobs.append((f"acs5_{year}_place", f"{year}/acs/acs5", "place"))

    ok = True
    for name, dataset, geo in jobs:
        dest = RAW / "census" / "acs" / "api" / f"{name}.json"
        if dest.exists() and not force:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            rows = (census_api_places(dataset, get) if geo == "place"
                    else census_api(dataset, get, geo))
            dest.write_text(json.dumps(rows))
            print(f"  ok    {dest.relative_to(RAW)} ({len(rows) - 1} rows)")
        except Exception as e:  # noqa: BLE001
            ok = False
            print(f"  FAIL  {name}: {e}")

    # Decennial 2000 long form (SF3): median value, median gross rent, 1999 median HH income, pop.
    sf3 = ["NAME", "H085001", "H063001", "P053001", "P001001"]
    for geo in ["state", "county", "place"]:
        dest = RAW / "census" / "dec2000" / f"sf3_{geo}.json"
        if dest.exists() and not force:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            rows = (census_api_places("2000/dec/sf3", sf3) if geo == "place"
                    else census_api("2000/dec/sf3", sf3, f"{geo}:*"))
            dest.write_text(json.dumps(rows))
            print(f"  ok    {dest.relative_to(RAW)} ({len(rows) - 1} rows)")
        except Exception as e:  # noqa: BLE001
            ok = False
            print(f"  FAIL  sf3 {geo}: {e}")
    return ok


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="download only these sources; use commas between them "
                         "(zillow, fhfa, census, bea, hud, fred, geo)")
    ap.add_argument("--force", action="store_true", help="download all the files again")
    ap.add_argument("--large", action="store_true", help="also download the Zillow ZIP-code files")
    args = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)
    only = set(args.only.split(",")) if args.only else None
    want = lambda src: only is None or src in only  # noqa: E731

    ok = True
    files = [f for f in static_files(args.large) if want(f[0])]
    current = None
    for source, name, url in files:
        if source != current:
            print(f"[{source}]")
            current = source
        ok &= fetch(url, RAW / source / name, args.force)

    for path in list((RAW / "bea").glob("*.zip")) + list((RAW / "geo").glob("*.zip")):
        if want(path.parent.name):
            unzip(path)

    if want("census"):
        print("[census] ACS summary files (keyless, 2021-2024)")
        ok &= download_acs_summary_files(args.force)
        if os.environ.get("CENSUS_API_KEY"):
            print("[census] Census API (ACS 2005+, decennial 2000)")
            ok &= download_census_api(args.force)
        else:
            print("[census] CENSUS_API_KEY not set: skipping ACS 2005-2020 and 2000 census history")

    print("done" if ok else "done, with failures (re-run to retry)")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
