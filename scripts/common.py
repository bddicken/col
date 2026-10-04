"""Shared paths, constants and loaders for the housing data pipeline."""

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"

# 50 states + DC: FIPS -> (USPS abbreviation, name)
STATES = {
    "01": ("AL", "Alabama"), "02": ("AK", "Alaska"), "04": ("AZ", "Arizona"),
    "05": ("AR", "Arkansas"), "06": ("CA", "California"), "08": ("CO", "Colorado"),
    "09": ("CT", "Connecticut"), "10": ("DE", "Delaware"), "11": ("DC", "District of Columbia"),
    "12": ("FL", "Florida"), "13": ("GA", "Georgia"), "15": ("HI", "Hawaii"),
    "16": ("ID", "Idaho"), "17": ("IL", "Illinois"), "18": ("IN", "Indiana"),
    "19": ("IA", "Iowa"), "20": ("KS", "Kansas"), "21": ("KY", "Kentucky"),
    "22": ("LA", "Louisiana"), "23": ("ME", "Maine"), "24": ("MD", "Maryland"),
    "25": ("MA", "Massachusetts"), "26": ("MI", "Michigan"), "27": ("MN", "Minnesota"),
    "28": ("MS", "Mississippi"), "29": ("MO", "Missouri"), "30": ("MT", "Montana"),
    "31": ("NE", "Nebraska"), "32": ("NV", "Nevada"), "33": ("NH", "New Hampshire"),
    "34": ("NJ", "New Jersey"), "35": ("NM", "New Mexico"), "36": ("NY", "New York"),
    "37": ("NC", "North Carolina"), "38": ("ND", "North Dakota"), "39": ("OH", "Ohio"),
    "40": ("OK", "Oklahoma"), "41": ("OR", "Oregon"), "42": ("PA", "Pennsylvania"),
    "44": ("RI", "Rhode Island"), "45": ("SC", "South Carolina"), "46": ("SD", "South Dakota"),
    "47": ("TN", "Tennessee"), "48": ("TX", "Texas"), "49": ("UT", "Utah"),
    "50": ("VT", "Vermont"), "51": ("VA", "Virginia"), "53": ("WA", "Washington"),
    "54": ("WV", "West Virginia"), "55": ("WI", "Wisconsin"), "56": ("WY", "Wyoming"),
}
ABBR_TO_FIPS = {abbr: fips for fips, (abbr, _) in STATES.items()}
NAME_TO_FIPS = {name: fips for fips, (_, name) in STATES.items()}

# ACS variables pulled from both the keyless summary files and the Census API.
ACS_VARS = {
    "B25077": "median_value",   # median value, owner-occupied units ($)
    "B25064": "median_rent",    # median gross rent ($/month)
    "B19013": "median_income",  # median household income ($)
    "B01003": "population",     # total population
}

# 2000 census long form (SF3) equivalents, pulled only with CENSUS_API_KEY.
DEC2000_VARS = {
    "H085001": "median_value",
    "H063001": "median_rent",
    "P053001": "median_income",  # 1999 income
    "P001001": "population",
}

ZHVI_FILE = "{geo}_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv"
ZORI_FILE = "{geo}_zori_uc_sfrcondomfr_sm_month.csv"


# ---------------------------------------------------------------- loaders

def load_zillow(path, id_cols_dtype=None):
    """Read a wide Zillow CSV. Returns (meta DataFrame, values DataFrame with
    a monthly PeriodIndex on columns), both indexed by RegionID."""
    df = pd.read_csv(path, dtype=id_cols_dtype or {})
    date_cols = [c for c in df.columns if c[:2] in ("19", "20") and c[4] == "-"]
    df = df.set_index("RegionID")
    values = df[date_cols].astype(float)
    values.columns = pd.PeriodIndex(date_cols, freq="M")
    meta = df.drop(columns=date_cols)
    return meta, values


def annual_mean(values):
    """Monthly wide frame -> annual mean (columns = int years). Years with no
    data stay NaN; a partial current year averages the months available."""
    years = values.columns.year
    return values.T.groupby(years).mean().T


def zillow_partial_year(values):
    """(year, months_available) for the latest year if it is incomplete."""
    last = values.columns.max()
    return (last.year, last.month) if last.month < 12 else None


def hpi_backcast(zillow, hpi):
    """Extend an annual Zillow series back in time with a price index. With `a`
    the first year both exist: value_y = zillow_a * hpi_y / hpi_a for y < a.
    Returns (Series, a); a is None when the two never overlap."""
    z, h = zillow.dropna(), hpi.dropna()
    common = [y for y in z.index if y in h.index]
    if not common:
        return z, None
    a = min(common)
    back = z[a] * h[h.index < a] / h[a]
    return pd.concat([back, z]).sort_index(), a


def chain_index(primary, fallback):
    """Fill years before `primary` starts (or all years, if it is empty) by
    chaining `fallback`'s growth onto primary's first value."""
    p, f = primary.dropna(), fallback.dropna()
    if p.empty:
        return f
    y0 = p.index.min()
    if y0 not in f.index:
        return p
    early = p[y0] * f[f.index < y0] / f[y0]
    return pd.concat([early, p]).sort_index()


def benchmark_factors(raw, census, anchor):
    """Multipliers that bend an HPI backcast through the decennial census
    medians for 1980 and 1990 (rescaled to Zillow's level using the 2000
    Zillow/Census ratio). 1.0 from the Zillow anchor year on, log-linear between
    benchmarks, held constant before the earliest one. Year-indexed Series."""
    years = [y for y in raw.index if y < anchor]
    if not years:
        return pd.Series(dtype=float)
    fac = {anchor: 1.0}
    if census is not None and 2000 in raw.index and pd.notna(census.get(2000)):
        k = raw[2000] / census[2000]
        for b in (1980, 1990):
            if b < anchor and b in raw.index and pd.notna(census.get(b)):
                fac[b] = k * census[b] / raw[b]
    xs = sorted(fac)
    logs = np.interp(years, xs, [math.log(fac[x]) for x in xs])
    return pd.Series(np.exp(logs), index=years)


def load_acs():
    """Load every Census survey extract into one long frame with columns
    [survey, year, geo_id, var, value]. Sources: keyless ACS summary files
    (acs/sf/*.dat), ACS via the Census API (acs/api/*.json) and the 2000
    census SF3 via the API (dec2000/*.json, survey 'dec2000')."""
    frames = []
    for path in sorted((RAW / "census" / "acs" / "sf").glob("*.dat")):
        # acs1_2024_b25077.dat
        survey, year, table = path.stem.split("_")
        df = pd.read_csv(path, sep="|", dtype=str)
        est = f"{table.upper()}_E001"
        frames.append(pd.DataFrame({
            "survey": survey, "year": int(year),
            "geo_id": df["GEO_ID"].map(normalize_geo_id),
            "var": ACS_VARS[table.upper()],
            "value": pd.to_numeric(df[est], errors="coerce"),
        }))
    for path in sorted((RAW / "census" / "acs" / "api").glob("*.json")):
        # acs5_2015_place.json
        survey, year, _ = path.stem.split("_")
        rows = json.loads(path.read_text())
        df = pd.DataFrame(rows[1:], columns=rows[0])
        df["geo_id"] = api_geo_ids(df)
        for table, var in ACS_VARS.items():
            col = f"{table}_001E"
            if col in df:
                frames.append(pd.DataFrame({
                    "survey": survey, "year": int(year), "geo_id": df["geo_id"],
                    "var": var, "value": pd.to_numeric(df[col], errors="coerce"),
                }))
    for path in sorted((RAW / "census" / "dec2000").glob("sf3_*.json")):
        rows = json.loads(path.read_text())
        df = pd.DataFrame(rows[1:], columns=rows[0])
        df["geo_id"] = api_geo_ids(df)
        for col, var in DEC2000_VARS.items():
            frames.append(pd.DataFrame({
                "survey": "dec2000", "year": 2000, "geo_id": df["geo_id"],
                "var": var, "value": pd.to_numeric(df[col], errors="coerce"),
            }))
    if not frames:
        return pd.DataFrame(columns=["survey", "year", "geo_id", "var", "value"])
    out = pd.concat(frames, ignore_index=True)
    # Census uses large negative sentinels (e.g. -666666666) for "not available".
    out.loc[out["value"] < 0, "value"] = float("nan")
    return out.dropna(subset=["value"]).drop_duplicates(["survey", "year", "geo_id", "var"])


def normalize_geo_id(geo_id):
    """'0400000US06' -> 'state:06', '0500000US06037' -> 'county:06037',
    '1600000US0644000' -> 'place:0644000', '0100000US' -> 'us'."""
    if geo_id.startswith("0100000US"):
        return "us"
    prefix, _, code = geo_id.partition("US")
    kind = {"0400000": "state", "0500000": "county", "1600000": "place"}.get(prefix)
    return f"{kind}:{code}" if kind else None


def api_geo_ids(df):
    if "place" in df:
        return "place:" + df["state"] + df["place"]
    if "county" in df:
        return "county:" + df["state"] + df["county"]
    if "state" in df:
        return "state:" + df["state"]
    return pd.Series("us", index=df.index)


def load_cpi_annual():
    """CPI-U (all items, SA) annual average from FRED CPIAUCSL."""
    df = pd.read_csv(RAW / "fred" / "CPIAUCSL.csv", parse_dates=["observation_date"])
    df = df.dropna()
    return df.groupby(df["observation_date"].dt.year)["CPIAUCSL"].mean()


def load_fhfa_master():
    return pd.read_csv(RAW / "fhfa" / "hpi_master.csv", low_memory=False)


# ---------------------------------------------------------------- output

def series(s, years, digits=0):
    """Align a year-indexed Series to `years`, as a JSON-safe list."""
    out = []
    for y in years:
        v = s.get(y) if s is not None else None
        out.append(clean(v, digits))
    return out


def clean(v, digits=0):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f):
        return None
    return int(round(f)) if digits == 0 else round(f, digits)


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, separators=(",", ":")))
    print(f"  wrote {path.relative_to(ROOT)} ({path.stat().st_size / 1e6:.1f} MB)")


def write_csv(path, df):
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    print(f"  wrote {path.relative_to(ROOT)} ({len(df):,} rows)")
