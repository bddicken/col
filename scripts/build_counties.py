"""Build data/processed/counties.json and counties_annual.csv.

Counties are keyed by 5-digit FIPS matching the `id` of geometries in
us-atlas counties-10m.json (2017 boundaries, so Connecticut uses its old
counties, which is also what Zillow and older HUD/FHFA vintages use).

Annual `home_value` per county (nominal $):
  * Zillow years (2000+ for most counties): ZHVI annual mean
  * Earlier years back to 1975: the FHFA annual county HPI (chained onto the
    state HPI for years before the county index starts, or entirely for
    Connecticut, whose FHFA county file uses the 2022 planning regions),
    scaled to the first Zillow year, then multiplied by the state's census
    benchmark factors (see build_states.py) so counties stay consistent with
    their state.
`fmr_2br`: HUD Fair Market Rent, 2-bedroom, by fiscal year (1983+).
"""

import json
from datetime import date

import pandas as pd

import build_states
from common import (PROCESSED, RAW, STATES, ZHVI_FILE, ZORI_FILE, annual_mean, chain_index,
                    hpi_backcast, load_acs, load_zillow, series, write_csv, write_json,
                    zillow_partial_year)

FIRST_YEAR = 1975


def atlas_counties():
    topo = json.loads((RAW / "geo" / "counties-10m.json").read_text())
    geoms = topo["objects"]["counties"]["geometries"]
    return {g["id"]: g["properties"]["name"] for g in geoms if g["id"][:2] in STATES}


def zillow_counties(kind):
    path = RAW / "zillow" / (ZHVI_FILE if kind == "zhvi" else ZORI_FILE).format(geo="County")
    meta, values = load_zillow(path, {"StateCodeFIPS": str, "MunicipalCodeFIPS": str})
    fips = meta.StateCodeFIPS.str.zfill(2) + meta.MunicipalCodeFIPS.str.zfill(3)
    values.index = fips
    meta.index = fips
    return meta, values


def fhfa_county_hpi():
    df = pd.read_excel(RAW / "fhfa" / "hpi_at_county.xlsx", header=5, dtype={"FIPS code": str})
    df = df.rename(columns={"FIPS code": "fips", "HPI": "hpi"})
    df["hpi"] = pd.to_numeric(df.hpi, errors="coerce")
    df["Year"] = pd.to_numeric(df.Year, errors="coerce")
    df = df.dropna(subset=["fips", "Year", "hpi"])
    return df.pivot_table(index="fips", columns="Year", values="hpi")


def hud_fmr_2br():
    """2-bedroom FMR per county per fiscal year. New England FMRs are set per
    town; those are collapsed to the county median."""
    df = pd.read_csv(RAW / "hud" / "FMR_All_1983_2027.csv", dtype=str, encoding="latin-1")
    # fips2024 still uses Connecticut's pre-2022 counties; fall back to fips2027.
    key = df.fips2024.where(df.fips2024.notna() & (df.fips2024.str.len() == 10), df.fips2027)
    df["county_fips"] = key.str[:5]
    cols = {}
    for c in df.columns:
        if c.startswith("fmr") and c.endswith("_2"):
            yy = int(c[3:5])
            cols[c] = 1900 + yy if yy >= 80 else 2000 + yy
    vals = df[list(cols)].apply(pd.to_numeric, errors="coerce").rename(columns=cols)
    vals["county_fips"] = df.county_fips
    return vals.groupby("county_fips").median()


def build():
    print("[counties]")
    names = atlas_counties()
    zmeta, zhvi = zillow_counties("zhvi")
    _, zori = zillow_counties("zori")
    zhvi_a, zori_a = annual_mean(zhvi), annual_mean(zori)
    hpi = fhfa_county_hpi()
    state_hpi = build_states.fhfa_states()
    state_homes = build_states.state_home_values(hpi=state_hpi)
    fmr = hud_fmr_2br()
    acs = load_acs()
    acs5 = acs[acs.survey.isin(["acs5", "dec2000"]) & acs.geo_id.str.startswith("county:", na=False)]
    acs5 = acs5.assign(fips=acs5.geo_id.str[7:]).pivot_table(index=["fips", "var"], columns="year", values="value")

    last_year = max(int(zhvi_a.columns.max()), int(fmr.columns.max()))
    years = list(range(FIRST_YEAR, last_year + 1))

    def row_or_none(df, k):
        return df.loc[k] if k in df.index else None

    def acs_series(fips, var):
        try:
            return acs5.loc[(fips, var)]
        except KeyError:
            return None

    records, rows = [], []
    for fips in sorted(names):
        z = row_or_none(zhvi_a, fips)
        h_county = row_or_none(hpi, fips)
        h_county = h_county.dropna() if h_county is not None else pd.Series(dtype=float)
        h_state = state_hpi.loc[fips[:2]] if fips[:2] in state_hpi.index else pd.Series(dtype=float)
        anchor = None
        home = pd.Series(dtype=float)
        if z is not None:
            raw, anchor = hpi_backcast(z, chain_index(h_county, h_state))
            factors = state_homes[fips[:2]][2]
            home = raw * factors.reindex(raw.index).fillna(1.0)
            home = home[home.index >= FIRST_YEAR]
        county_hpi_from = int(h_county.index.min()) if not h_county.empty else None

        def source(y):
            if anchor is None or y >= anchor:
                return "zillow_zhvi"
            if county_hpi_from is not None and y >= county_hpi_from:
                return "fhfa_county_hpi"
            return "fhfa_state_hpi"
        abbr = STATES[fips[:2]][0]
        rec = {
            "fips": fips, "name": names[fips], "state": abbr,
            "metro": zmeta.Metro.get(fips) if fips in zmeta.index and pd.notna(zmeta.Metro.get(fips)) else None,
            "home_value": series(home, years),
            "zillow_from": anchor,
            "county_hpi_from": county_hpi_from,
            "rent": series(row_or_none(zori_a, fips), years),
            "fmr_2br": series(row_or_none(fmr, fips), years),
            "census_median_value": series(acs_series(fips, "median_value"), years),
            "census_median_rent": series(acs_series(fips, "median_rent"), years),
            "census_median_income": series(acs_series(fips, "median_income"), years),
            "census_population": series(acs_series(fips, "population"), years),
        }
        records.append(rec)
        for i, y in enumerate(years):
            rows.append({
                "fips": fips, "name": rec["name"], "state": abbr, "year": y,
                "home_value": rec["home_value"][i],
                "home_value_source": source(y) if rec["home_value"][i] is not None else None,
                "rent": rec["rent"][i], "fmr_2br": rec["fmr_2br"][i],
                "census_median_value": rec["census_median_value"][i],
                "census_median_rent": rec["census_median_rent"][i],
                "census_median_income": rec["census_median_income"][i],
                "census_population": rec["census_population"][i],
            })

    with_zillow = sum(1 for r in records if any(v is not None for v in r["home_value"]))
    unmatched = sorted(set(zhvi.index) - set(names))
    print(f"  {len(records)} counties, {with_zillow} with Zillow values; "
          f"{len(unmatched)} Zillow counties not in us-atlas: {unmatched[:10]}")

    partial = zillow_partial_year(zhvi)
    write_json(PROCESSED / "counties.json", {
        "meta": {
            "generated": date.today().isoformat(),
            "key": "fips = us-atlas counties-10m.json geometry id",
            "home_value": "Nominal $. From `zillow_from`: Zillow ZHVI annual mean. Earlier: FHFA "
                          "county HPI (from `county_hpi_from`; state HPI before that), scaled to the "
                          "first Zillow year and multiplied by the state's census benchmark factors.",
            "rent": "Zillow ZORI annual mean (2015+), $/month.",
            "fmr_2br": "HUD Fair Market Rent, 2-bedroom, by fiscal year, $/month (~40th percentile rent).",
            "census_*": "Census Bureau medians: ACS 5-year estimates by end year, plus the 2000 "
                        "census (SF3) when downloaded with CENSUS_API_KEY.",
            "partial_year": {"year": partial[0], "months": partial[1]} if partial else None,
            "attribution": "Zillow; FHFA; HUD; U.S. Census Bureau",
        },
        "years": years,
        "counties": records,
    })
    write_csv(PROCESSED / "counties_annual.csv", pd.DataFrame(rows))


if __name__ == "__main__":
    build()
