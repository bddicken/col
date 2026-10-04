"""Build data/processed/states.json, states_annual.csv and states_monthly.csv.

Annual `home_value` per state (nominal $):
  * Zillow years (2000+; 2002-2009 for MT, NM, ND, WY): ZHVI annual mean.
    The latest year is a partial-year mean.
  * Earlier years back to 1975: the FHFA all-transactions HPI, scaled to the
    first Zillow year, then benchmarked through the 1980 and 1990 census
    medians. FHFA is a constant-quality repeat-sales index, so on its own it
    drifts from "typical home" medians (+26% vs census by 1980 on average,
    range 0.74x-1.88x); the benchmark keeps FHFA's year-to-year shape but
    matches census levels in benchmark years.
"""

import re
from datetime import date

import pandas as pd

from common import (ABBR_TO_FIPS, NAME_TO_FIPS, PROCESSED, RAW, STATES, ZHVI_FILE,
                    annual_mean, benchmark_factors, clean, hpi_backcast, load_acs,
                    load_cpi_annual, load_fhfa_master, load_zillow, series, write_csv,
                    write_json, zillow_partial_year)

FIRST_YEAR = 1975


def zillow_states():
    meta, values = load_zillow(RAW / "zillow" / ZHVI_FILE.format(geo="State"))
    values.index = meta["RegionName"].map(NAME_TO_FIPS)
    values = values[values.index.notna()]
    _, metro = load_zillow(RAW / "zillow" / ZHVI_FILE.format(geo="Metro"))
    values.loc["us"] = metro.loc[102001]  # RegionID 102001 = United States
    return values


def fhfa_states():
    """Annual mean of the quarterly all-transactions index (NSA), keyed by state FIPS / 'us'."""
    m = load_fhfa_master()
    m = m[(m.hpi_type == "traditional") & (m.hpi_flavor == "all-transactions")
          & (m.frequency == "quarterly")]
    st = m[m.level == "State"].copy()
    st["key"] = st.place_id.map(ABBR_TO_FIPS)
    us = m[(m.level == "USA or Census Division") & (m.place_id == "USA")].copy()
    us["key"] = "us"
    both = pd.concat([st, us]).dropna(subset=["key"])
    return both.groupby(["key", "yr"]).index_nsa.mean().unstack()


def coh_table(name):
    """Census 'Historical Census of Housing' fixed-width tables (1940-2000) ->
    DataFrame indexed by state FIPS / 'us', columns = decennial years."""
    text = (RAW / "census" / name).read_text(errors="replace")
    years, rows = None, {}
    for line in text.splitlines():
        if years is None and re.match(r"^\s+(\d{4}\s+){3,}", line):
            years = [int(y) for y in line.split()]
            continue
        if not years or "$" not in line:
            continue
        label = re.split(r"\s{2,}|\s\$", line.strip())[0].strip()
        nums = re.findall(r"\$[\d,]+|\bNA\b", line)
        if len(nums) != len(years):
            continue
        key = "us" if label == "United States" else NAME_TO_FIPS.get(
            label.replace("Dist. of Columbia", "District of Columbia"))
        if key:
            rows[key] = [None if n == "NA" else int(n.strip("$").replace(",", "")) for n in nums]
    return pd.DataFrame.from_dict(rows, orient="index", columns=years)


def fred_income():
    out = {}
    for fips, (abbr, _) in list(STATES.items()) + [("us", ("", ""))]:
        sid = "MEHOINUSA646N" if fips == "us" else f"MEHOINUS{abbr}A646N"
        path = RAW / "fred" / f"{sid}.csv"
        if path.exists():
            df = pd.read_csv(path, parse_dates=["observation_date"]).dropna()
            out[fips] = pd.Series(df[sid].values, index=df.observation_date.dt.year)
    return out


def bea_rpp():
    """BEA regional price parities: {fips: {'all': Series, 'housing': Series}}."""
    path = next((RAW / "bea" / "SARPP").glob("SARPP_STATE_*.csv"))
    df = pd.read_csv(path, dtype={"GeoFIPS": str}, encoding="latin-1")
    df = df[pd.to_numeric(df.LineCode, errors="coerce").isin([1, 3])]
    df["GeoFIPS"] = df.GeoFIPS.str.strip().str.strip('"')
    year_cols = [c for c in df.columns if c.isdigit()]
    out = {}
    for _, r in df.iterrows():
        key = "us" if r.GeoFIPS == "00000" else r.GeoFIPS[:2]
        s = pd.to_numeric(r[year_cols], errors="coerce")
        s.index = s.index.astype(int)
        out.setdefault(key, {})["all" if int(r.LineCode) == 1 else "housing"] = s
    return out


def state_home_values(zhvi_annual=None, hpi=None, coh_value=None):
    """{key: (home_value Series, zillow_anchor_year, benchmark factor Series)}
    for 'us' and every state FIPS. Counties reuse the factors."""
    zhvi_annual = annual_mean(zillow_states()) if zhvi_annual is None else zhvi_annual
    hpi = fhfa_states() if hpi is None else hpi
    coh_value = coh_table("coh_values_unadj.txt") if coh_value is None else coh_value
    out = {}
    for key in ["us"] + sorted(STATES):
        z = zhvi_annual.loc[key] if key in zhvi_annual.index else pd.Series(dtype=float)
        h = hpi.loc[key] if key in hpi.index else pd.Series(dtype=float)
        census = coh_value.loc[key] if key in coh_value.index else None
        raw, anchor = hpi_backcast(z, h)
        factors = benchmark_factors(raw, census, anchor) if anchor else pd.Series(dtype=float)
        home = raw * factors.reindex(raw.index).fillna(1.0)
        out[key] = (home[home.index >= FIRST_YEAR], anchor, factors)
    return out


def build():
    print("[states]")
    zhvi = zillow_states()
    zhvi_annual = annual_mean(zhvi)
    hpi = fhfa_states()
    coh_value = coh_table("coh_values_unadj.txt")
    homes = state_home_values(zhvi_annual, hpi, coh_value)
    coh_rent = coh_table("coh_grossrents_unadj.txt")
    income = fred_income()
    rpp = bea_rpp()
    cpi = load_cpi_annual()
    acs = load_acs()
    acs1 = acs[acs.survey == "acs1"].pivot_table(index=["geo_id", "var"], columns="year", values="value")

    last_year = int(zhvi_annual.columns.max())
    years = list(range(FIRST_YEAR, last_year + 1))
    months = [str(p) for p in zhvi.columns]

    def acs_series(key, var):
        gid = "us" if key == "us" else f"state:{key}"
        try:
            return acs1.loc[(gid, var)]
        except KeyError:
            return None

    records, rows, monthly_rows = [], [], []
    for key in ["us"] + sorted(STATES):
        abbr, name = ("US", "United States") if key == "us" else STATES[key]
        h = hpi.loc[key] if key in hpi.index else pd.Series(dtype=float)
        home, anchor, _ = homes[key]
        inc = income.get(key)
        ratio = (home / inc) if inc is not None else None

        rec = {
            "fips": None if key == "us" else key, "abbr": abbr, "name": name,
            "home_value": series(home, years),
            "zillow_from": anchor,
            "home_value_monthly": [clean(v) for v in zhvi.loc[key]] if key in zhvi.index else None,
            "hpi": series(h, years, 2),
            "median_income": series(inc, years),
            "value_to_income": series(ratio, years, 2) if ratio is not None else None,
            "acs_median_value": series(acs_series(key, "median_value"), years),
            "acs_median_rent": series(acs_series(key, "median_rent"), years),
            "acs_median_income": series(acs_series(key, "median_income"), years),
            "acs_population": series(acs_series(key, "population"), years),
            "rpp_all": series(rpp.get(key, {}).get("all"), years, 1),
            "rpp_housing": series(rpp.get(key, {}).get("housing"), years, 1),
            "census_decennial_value": {str(y): clean(v) for y, v in coh_value.loc[key].items()}
                if key in coh_value.index else None,
            "census_decennial_rent": {str(y): clean(v) for y, v in coh_rent.loc[key].items()}
                if key in coh_rent.index else None,
        }
        records.append(rec)

        for i, y in enumerate(years):
            rows.append({
                "fips": rec["fips"], "abbr": abbr, "name": name, "year": y,
                "home_value": rec["home_value"][i],
                "home_value_source": ("zillow_zhvi" if anchor is None or y >= anchor else "fhfa_hpi_census_benchmarked")
                    if rec["home_value"][i] is not None else None,
                "hpi": rec["hpi"][i],
                "median_income": rec["median_income"][i],
                "value_to_income": rec["value_to_income"][i] if rec["value_to_income"] else None,
                "acs_median_value": rec["acs_median_value"][i],
                "acs_median_rent": rec["acs_median_rent"][i],
                "acs_median_income": rec["acs_median_income"][i],
                "acs_population": rec["acs_population"][i],
                "rpp_all": rec["rpp_all"][i], "rpp_housing": rec["rpp_housing"][i],
                "cpi": clean(cpi.get(y), 3),
            })
        if rec["home_value_monthly"]:
            for m, v in zip(months, rec["home_value_monthly"]):
                monthly_rows.append({"fips": rec["fips"], "abbr": abbr, "month": m, "zhvi": v})

    partial = zillow_partial_year(zhvi)
    out = {
        "meta": {
            "generated": date.today().isoformat(),
            "years": "aligned index for every annual array below",
            "home_value": "Nominal $. From `zillow_from` (2000 for most states): Zillow ZHVI annual "
                          "mean (all homes, middle tier). Earlier years: FHFA all-transactions HPI "
                          "scaled to the first Zillow year and benchmarked through the 1980/1990 "
                          "census medians (see scripts/build_states.py).",
            "home_value_monthly": "Zillow ZHVI monthly, aligned to `months`.",
            "hpi": "FHFA all-transactions house price index, annual mean (NSA, 1980Q1=100).",
            "median_income": "Median household income, nominal $ (Census CPS via FRED).",
            "value_to_income": "home_value / median_income.",
            "acs_*": "American Community Survey 1-year estimates (B25077, B25064, B19013, B01003).",
            "rpp_*": "BEA Regional Price Parities (US=100). Comparable across states within a year, not across years.",
            "census_decennial_*": "Census Historical Census of Housing medians, 1940-2000 (nominal $).",
            "cpi": "CPI-U annual average (FRED CPIAUCSL) for converting to real dollars.",
            "partial_year": {"year": partial[0], "months": partial[1]} if partial else None,
            "attribution": "Zillow; FHFA; U.S. Census Bureau; BEA; FRED",
        },
        "years": years,
        "months": months,
        "cpi": series(cpi, years, 3),
        "us": records[0],
        "states": records[1:],
    }
    write_json(PROCESSED / "states.json", out)
    write_csv(PROCESSED / "states_annual.csv", pd.DataFrame(rows))
    write_csv(PROCESSED / "states_monthly.csv", pd.DataFrame(monthly_rows))
    write_json(PROCESSED / "cpi.json", {"source": "FRED CPIAUCSL annual mean",
                                        "cpi": {str(y): round(v, 3) for y, v in cpi.items()}})


if __name__ == "__main__":
    build()
