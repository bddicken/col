"""Make one file for each state for the state view of the app:
data/processed/web/by_state/{state_fips}.json.

Each file contains the counties and the cities of one state. All the value
lists use the `years` list of states.json. The file does not include cities
with the `county` match, because their location is only the county center.
"""

import json

from common import PROCESSED, STATES

CITY_MATCHES = {"place", "place_alias", "cousub", "override"}


def realign(values, src_years, dst_years):
    if values is None:
        return None
    by_year = dict(zip(src_years, values))
    out = [by_year.get(y) for y in dst_years]
    return out if any(v is not None for v in out) else None


def build():
    print("[by_state]")
    years = json.loads((PROCESSED / "states.json").read_text())["years"]
    counties = json.loads((PROCESSED / "counties.json").read_text())
    cities = json.loads((PROCESSED / "cities.json").read_text())
    abbr_to_fips = {abbr: fips for fips, (abbr, _) in STATES.items()}

    per_state = {fips: {"counties": [], "cities": []} for fips in STATES}
    for c in counties["counties"]:
        per_state[c["fips"][:2]]["counties"].append({
            "fips": c["fips"], "name": c["name"],
            "home_value": realign(c["home_value"], counties["years"], years),
            "zillow_from": c["zillow_from"],
        })
    skipped = 0
    for c in cities["cities"]:
        fips = abbr_to_fips.get(c["state"])
        if fips is None or c["match"] not in CITY_MATCHES or c["lat"] is None:
            skipped += 1
            continue
        per_state[fips]["cities"].append({
            "id": c["id"], "name": c["name"], "county": c["county"],
            "lat": c["lat"], "lon": c["lon"], "population": c["population"],
            "home_value": realign(c["home_value"], cities["years"], years),
        })

    out_dir = PROCESSED / "web" / "by_state"
    out_dir.mkdir(parents=True, exist_ok=True)
    for fips, d in per_state.items():
        (out_dir / f"{fips}.json").write_text(json.dumps(
            {"fips": fips, "years": years, **d}, separators=(",", ":")))
    sizes = sorted(((out_dir / f"{f}.json").stat().st_size, STATES[f][0]) for f in per_state)
    print(f"  wrote {len(per_state)} files to data/processed/web/by_state/ "
          f"(largest {sizes[-1][1]} {sizes[-1][0] / 1e6:.1f} MB); "
          f"skipped {skipped} cities with approximate locations")


if __name__ == "__main__":
    build()
