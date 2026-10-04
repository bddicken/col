"""Make cities.json, cities_annual.csv, and city_crosswalk.csv.

The Zillow city files do not give a location or a Census code. The script
finds each city in the Census Gazetteer. It tries these methods in sequence:
  1. override     A manual location from scripts/city_overrides.csv.
  2. place        A Census place with the same name in the same state.
  3. place_alias  A different form of the Census name. Examples:
                  "Nashville-Davidson metropolitan government (balance)",
                  "Urban Honolulu", "San Buenaventura (Ventura)".
  4. cousub       A county subdivision, for example a township in NJ, PA, MI,
                  or New England.
  5. county       The center of the Zillow county. This location is approximate.

If two or more candidates have the same name, the script uses the candidate
nearest to the Zillow county. The script rejects a candidate that is too far
from the Zillow county (more than 3 times the county radius, plus 50 km).
This rule is necessary because many Zillow city names are also the names of
other places in the same state.
"""

import math
import re
import unicodedata
from datetime import date

import pandas as pd

from common import (PROCESSED, RAW, ROOT, STATES, ZHVI_FILE, ZORI_FILE, annual_mean, clean,
                    load_acs, load_zillow, series, write_csv, write_json, zillow_partial_year)

OVERRIDES = ROOT / "scripts" / "city_overrides.csv"
FIRST_YEAR = 2000

LSAD_SUFFIXES = sorted([
    "city and borough", "consolidated government", "unified government",
    "metropolitan government", "metro government", "urban county", "charter township",
    "township", "city", "town", "village", "borough", "municipality", "cdp", "comunidad",
    "zona urbana", "plantation", "gore", "grant", "location", "purchase", "ccd",
    "unorganized territory", "reservation", "district", "county", "parish", "census area",
], key=len, reverse=True)
SUFFIX_RE = re.compile(r"\s+(" + "|".join(LSAD_SUFFIXES) + r")$", re.I)
WORD_SUBS = {"saint": "st", "sainte": "ste", "mount": "mt", "fort": "ft"}


def norm(name):
    """Comparison key: ASCII, lowercase, no punctuation or spaces, common abbreviations."""
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().lower()
    s = s.replace("&", " and ")
    s = re.sub(r"[.'`,]", "", s)
    s = re.sub(r"[-/]", " ", s)
    words = [WORD_SUBS.get(w, w) for w in s.split()]
    return "".join(words)


def strip_lsad(name):
    name = re.sub(r"\s*\(balance\)\s*$", "", name.strip())
    return SUFFIX_RE.sub("", name).strip()


def name_keys(full_name):
    """(primary keys, alias keys) for a Gazetteer place/cousub name."""
    base = strip_lsad(full_name)
    primary = {norm(base), norm(full_name)}
    alias = {norm(strip_lsad(base))}  # "Weymouth Town city", "Boise City city", "Mililani Town CDP"
    m = re.match(r"^(.*?)\s*\((.+)\)$", base)  # "San Buenaventura (Ventura)"
    if m:
        primary |= {norm(m.group(1)), norm(m.group(2))}
    if base.lower().startswith("urban "):     # "Urban Honolulu"
        alias.add(norm(base[6:]))
    consolidated = ("(balance)" in full_name or " County" in full_name
                    or re.search(r"government|urban county", full_name, re.I))
    if consolidated:
        head = re.split(r"[-/]", base)[0]     # "Nashville-Davidson" -> "Nashville"
        alias.add(norm(head))
    return primary, alias - primary


def haversine_km(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 12742 * math.asin(math.sqrt(a))


def read_gazetteer(layer):
    path = next((RAW / "geo" / f"2025_Gaz_{layer}_national").glob("*.txt"))
    df = pd.read_csv(path, sep="|", dtype=str, encoding="latin-1")
    df.columns = [c.strip() for c in df.columns]
    df["lat"] = df.INTPTLAT.astype(float)
    df["lon"] = df.INTPTLONG.astype(float)
    return df


class Index:
    """(state, key) -> list of candidate rows, for primary and alias keys."""

    def __init__(self, df, kind):
        self.primary, self.alias, self.by_geoid = {}, {}, {}
        for r in df.itertuples(index=False):
            cand = {"geoid": r.GEOID, "name": r.NAME, "lat": r.lat, "lon": r.lon, "kind": kind,
                    "incorporated": getattr(r, "FUNCSTAT", "") in ("A", "B", "C", "G"),
                    "aland": float(r.ALAND)}
            self.by_geoid[r.GEOID] = cand
            primary, alias = name_keys(r.NAME)
            for k in primary:
                self.primary.setdefault((r.USPS, k), []).append(cand)
            for k in alias:
                self.alias.setdefault((r.USPS, k), []).append(cand)


def pick(cands, county_pt):
    """Choose among same-named candidates: nearest to the Zillow county centroid
    when known, otherwise prefer incorporated places, then larger land area."""
    if len(cands) == 1:
        return cands[0]
    if county_pt:
        return min(cands, key=lambda c: haversine_km(c["lat"], c["lon"], *county_pt))
    ranked = sorted(cands, key=lambda c: (not c["incorporated"], -c["aland"]))
    if ranked[0]["incorporated"] and not ranked[1]["incorporated"]:
        return ranked[0]
    return None  # genuinely ambiguous


def county_lookup():
    df = read_gazetteer("counties")
    out = {}
    for r in df.itertuples(index=False):
        radius_km = math.sqrt(float(r.ALAND) / 1e6 / math.pi)
        pt = {"geoid": r.GEOID, "lat": r.lat, "lon": r.lon, "max_km": 3 * radius_km + 50}
        out[(r.USPS, norm(r.NAME))] = pt
        out.setdefault((r.USPS, norm(strip_lsad(r.NAME))), pt)
    return out


def load_overrides():
    if not OVERRIDES.exists():
        return {}
    df = pd.read_csv(OVERRIDES, dtype=str, comment="#").fillna("")
    return {(r.state, r.zillow_name): r for r in df.itertuples(index=False)}


def match_cities(meta):
    places = Index(read_gazetteer("place"), "place")
    cousubs = Index(read_gazetteer("cousubs"), "cousub")
    counties = county_lookup()
    overrides = load_overrides()

    rows = []
    for region_id, r in meta.iterrows():
        st, name = r.State, r.RegionName
        county = None
        if isinstance(r.CountyName, str):
            county = counties.get((st, norm(r.CountyName))) or counties.get(
                (st, norm(strip_lsad(r.CountyName))))
        county_pt = (county["lat"], county["lon"]) if county else None
        keys = [(st, norm(name)), (st, norm(strip_lsad(name)))]  # "Clinton Township" -> "Clinton"

        def plausible(cands):
            if not county:
                return cands
            return [c for c in cands
                    if haversine_km(c["lat"], c["lon"], *county_pt) <= county["max_km"]]

        def lookup(index):
            # Pool every name variant so the right county's candidate competes.
            cands = {c["geoid"]: c for k in keys for c in index.get(k, [])}
            return plausible(list(cands.values()))

        hit, method = None, None
        ov = overrides.get((st, name))
        if ov is not None:
            if ov.geoid:
                hit = places.by_geoid.get(ov.geoid) or cousubs.by_geoid.get(ov.geoid)
                if hit and ov.lat and ov.lon:  # keep the Census match, move the point
                    hit = {**hit, "lat": float(ov.lat), "lon": float(ov.lon)}
            elif ov.lat and ov.lon:
                hit = {"geoid": None, "name": ov.note or name, "lat": float(ov.lat),
                       "lon": float(ov.lon), "kind": "manual"}
            method = "override" if hit else None
        def try_place():
            cands = lookup(places.primary)
            return (pick(cands, county_pt), "place") if cands else (None, None)

        def try_alias():
            cands = lookup(places.alias)
            return (pick(cands, county_pt), "place_alias") if cands else (None, None)

        def try_cousub():
            cands = lookup(cousubs.primary)
            if not cands or not (county_pt or len(cands) == 1):
                return None, None
            # Townships repeat within a state (many "Washington township"s), so
            # the county anchors the choice. Connecticut's old counties are gone
            # from the 2025 Gazetteer, so there a statewide-unique name has to do.
            same_county = [c for c in cands if county and c["geoid"][:5] == county["geoid"]]
            return pick(same_county or cands, county_pt), "cousub"

        # "Egg Harbor Township" is the township, not Egg Harbor City.
        order = ([try_cousub, try_place, try_alias] if "township" in name.lower()
                 else [try_place, try_alias, try_cousub])
        for attempt in order:
            if hit is not None:
                break
            hit, method = attempt()
        if hit is None and county:
            hit = {"geoid": None, "name": r.CountyName, "lat": county["lat"],
                   "lon": county["lon"], "kind": "county"}
            method = "county"

        dist = (round(haversine_km(hit["lat"], hit["lon"], *county_pt), 1)
                if hit and county_pt else None)
        rows.append({
            "RegionID": region_id, "RegionName": name, "State": st,
            "CountyName": r.CountyName, "Metro": r.Metro, "SizeRank": r.SizeRank,
            "method": method or "unmatched",
            "geoid": hit["geoid"] if hit else None,
            "census_name": hit["name"] if hit else None,
            "lat": round(hit["lat"], 5) if hit else None,
            "lon": round(hit["lon"], 5) if hit else None,
            "km_from_county_centroid": dist,
        })
    return pd.DataFrame(rows).set_index("RegionID")


def sparse(s):
    """Year-indexed Series -> {"2024": value} with only the years present, or None."""
    if s is None:
        return None
    out = {str(int(y)): clean(v) for y, v in s.items() if clean(v) is not None}
    return out or None


def build():
    print("[cities]")
    meta, zhvi = load_zillow(RAW / "zillow" / ZHVI_FILE.format(geo="City"))
    _, zori = load_zillow(RAW / "zillow" / ZORI_FILE.format(geo="City"))
    meta = meta[meta.State.isin({a for a, _ in STATES.values()})]
    zhvi = zhvi.loc[meta.index]
    zhvi_a, zori_a = annual_mean(zhvi), annual_mean(zori)

    xw = match_cities(meta)
    counts = xw.method.value_counts()
    print("  match methods:", ", ".join(f"{k}={v}" for k, v in counts.items()))
    top = xw[xw.SizeRank < 1000]
    print(f"  top-1000 by size: {(top.method.isin(['place', 'place_alias', 'override', 'cousub'])).sum()} "
          f"matched to a place/subdivision, {(top.method == 'county').sum()} county-centroid, "
          f"{(top.method == 'unmatched').sum()} unmatched")
    far = xw[(xw.km_from_county_centroid > 150) & (xw.method != "override")]
    print(f"  {len(far)} matches >150 km from their Zillow county centroid (check city_crosswalk.csv)")
    write_csv(PROCESSED / "city_crosswalk.csv", xw.reset_index().sort_values("SizeRank"))

    acs = load_acs()
    acs5 = acs[acs.survey.isin(["acs5", "dec2000"]) & acs.geo_id.str.startswith("place:", na=False)]
    acs5 = acs5.assign(geoid=acs5.geo_id.str[6:])
    acs_by = {var: g.pivot_table(index="geoid", columns="year", values="value")
              for var, g in acs5.groupby("var")}

    last_year = int(zhvi_a.columns.max())
    years = list(range(FIRST_YEAR, last_year + 1))

    def acs_row(var, geoid):
        t = acs_by.get(var)
        return t.loc[geoid] if t is not None and geoid in t.index else None

    records, rows = [], []
    for region_id, m in xw.sort_values("SizeRank").iterrows():
        if m.method == "unmatched":
            continue
        geoid = m.geoid if isinstance(m.geoid, str) and len(m.geoid) == 7 else None
        pop = acs_row("population", geoid) if geoid else None
        rent = zori_a.loc[region_id] if region_id in zori_a.index else None
        rec = {
            "id": int(region_id), "name": m.RegionName, "state": m.State,
            "county": m.CountyName if isinstance(m.CountyName, str) else None,
            "metro": m.Metro if isinstance(m.Metro, str) else None,
            "rank": int(m.SizeRank), "geoid": m.geoid if isinstance(m.geoid, str) else None,
            "lat": m.lat, "lon": m.lon, "match": m.method,
            "population": int(pop.dropna().iloc[-1]) if pop is not None and pop.notna().any() else None,
            "home_value": series(zhvi_a.loc[region_id], years),
            "rent": series(rent, years),
            "census_median_value": sparse(acs_row("median_value", geoid)) if geoid else None,
            "census_median_rent": sparse(acs_row("median_rent", geoid)) if geoid else None,
            "census_median_income": sparse(acs_row("median_income", geoid)) if geoid else None,
        }
        if all(v is None for v in rec["rent"]):
            rec["rent"] = None  # keeps cities.json small
        records.append(rec)
        for i, y in enumerate(years):
            if rec["home_value"][i] is None and not (rec["rent"] and rec["rent"][i]):
                continue
            acs_at = lambda k: (rec[k] or {}).get(str(y))  # noqa: E731
            rows.append({"id": rec["id"], "name": rec["name"], "state": rec["state"], "year": y,
                         "lat": rec["lat"], "lon": rec["lon"],
                         "home_value": rec["home_value"][i],
                         "rent": rec["rent"][i] if rec["rent"] else None,
                         "census_median_value": acs_at("census_median_value"),
                         "census_median_rent": acs_at("census_median_rent"),
                         "census_median_income": acs_at("census_median_income")})

    partial = zillow_partial_year(zhvi)
    write_json(PROCESSED / "cities.json", {
        "meta": {
            "generated": date.today().isoformat(),
            "home_value": "Zillow ZHVI annual mean, nominal $ (all homes, middle tier). 2000+.",
            "rent": "Zillow ZORI annual mean, $/month. 2015+.",
            "census_*": "Census Bureau medians for the matched Census place as {year: value}: ACS "
                        "5-year estimates by end year, plus the 2000 census (SF3) when downloaded "
                        "with CENSUS_API_KEY.",
            "population": "Latest Census population of the matched Census place.",
            "match": "How lat/lon was found: override, place, place_alias, cousub, or county "
                     "(county centroid; approximate). See city_crosswalk.csv.",
            "rank": "Zillow SizeRank (0 = largest).",
            "partial_year": {"year": partial[0], "months": partial[1]} if partial else None,
            "attribution": "Zillow; U.S. Census Bureau",
        },
        "years": years,
        "cities": records,
    })
    write_csv(PROCESSED / "cities_annual.csv", pd.DataFrame(rows))


if __name__ == "__main__":
    build()
