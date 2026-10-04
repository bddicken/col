# US Housing Cost Data

Data pipeline for a state, county and city heatmap / height map of US housing costs, 1975–present. See [DATA_SOURCES.md](DATA_SOURCES.md) for the research behind the source choices and their terms of use.

## Setup and run

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/download.py     # ~220 MB into data/raw/ (re-runs skip existing files)
.venv/bin/python scripts/process.py      # ~20 s, writes data/processed/
```

- `download.py --force` re-downloads everything, e.g. to pick up Zillow's monthly update.
- `--only zillow,fred` limits the download to the listed sources.
- `--large` adds Zillow ZIP-code files.

**Optional Census API key.** Get a free key at https://api.census.gov/data/key_signup.html, then run:

```bash
CENSUS_API_KEY=... .venv/bin/python scripts/download.py --only census
```

With a key, the download adds:

- ACS history: 2005–2024 for states, and 2009–2024 for counties and cities.
- 2000 census medians for counties and cities.

`process.py` uses this data automatically.

The key isn't stored anywhere in this project, and re-running `download.py` without one keeps the files already downloaded.

`data/` is not committed. It's rebuilt by the two commands above, and the app reads from `data/processed/`.

## Visualization app

`app/` is a Vite + three.js app that serves `data/processed/` directly:

```bash
cd app && npm install && npm run dev    # http://localhost:5173
```

It shows a 3D map of the states. Each state is raised in proportion to the selected metric, and its color shows the same value on a green → red scale. Controls:

- **Timeline:** play through 1975–2026, or scrub the slider or the trend line above it.
- **Metric:** home value (inflation-adjusted or nominal), price-to-income, or BEA cost of living.
- **Scale:** "All years" keeps one scale so you can see change over time. "Each year" rescales every year so you can compare places within a year.
- **Drill-down:** clicking a state flies into it. "Counties" shows county blocks. "Cities" shows one column per city (from 2000), with the 8 most populous cities labelled.
  - Inside a state, clicking a county, a city or a list row shows its history against the state.
  - The URL tracks the view (`#CA`, `#CA/cities`), so links and the browser back button work.
  - Esc or the "US Housing Costs" breadcrumb goes back to the US view.

Code layout:

- `src/scene.js`: three.js layers. States and counties are extruded prisms; cities are an instanced column mesh. Labels are HTML (CSS2D) with overlap culling.
- `src/main.js`: app state, navigation and UI.
- `src/charts.js`: the small SVG line charts.
- `src/data.js`: data loading and metric definitions.

## Layout

```
data/raw/        untouched source files, one folder per source
  zillow/ fhfa/ census/ bea/ hud/ fred/ geo/
data/processed/  app-ready output (below)
scripts/
  download.py          fetch raw data
  process.py           run all builders, copy map geometry
  build_states.py      states.json, states_annual.csv, states_monthly.csv, cpi.json
  build_counties.py    counties.json, counties_annual.csv
  build_cities.py      cities.json, cities_annual.csv, city_crosswalk.csv
  build_state_files.py by_state/{fips}.json for the app's drill-down
  city_overrides.csv   hand-fixed Zillow city -> location matches
  common.py            shared loaders and helpers
```

## Processed data

All money values are **nominal dollars**. Every JSON file has a `meta` block describing its fields. Annual arrays line up with that file's top-level `years` array, and `null` means no data. The latest year is an average of the months available so far (`meta.partial_year`).

| File | Rows | Key | Years |
|---|---|---|---|
| `states.json` | 50 states + DC, plus a `us` entry | `fips` (2-digit) matches `id` in `geo/states-10m.json` | 1975–2026, plus monthly values since 2000-01 |
| `counties.json` | 3,142 counties (3,071 with home values) | `fips` (5-digit) matches `id` in `geo/counties-10m.json` | 1975–2027 (fair market rents run through FY2027) |
| `cities.json` | 21,367 Zillow cities with lat/lon | `id` (Zillow RegionID); `geoid` is the Census place or county subdivision code | 2000–2026 |
| `*_annual.csv` | the same data in long (one row per place-year) format, for analysis | | |
| `city_crosswalk.csv` | how each Zillow city was located, for checking | | |
| `by_state/{fips}.json` | one state's counties and located cities, loaded by the app when you click into that state | | 1975–2026 |
| `cpi.json` | CPI-U annual average | | 1947–2026 |
| `geo/*.json` | us-atlas TopoJSON for states, counties and the nation. `*-albers-*` versions are pre-projected to 975×610 | | |

**`home_value`**, the main field to map, in each file:

- **States and counties:** Zillow's typical home value (ZHVI) from 2000 on. Before Zillow's data starts, it's extended back to 1975 with FHFA's house price index, adjusted to match the 1980 and 1990 census median values. The per-year source is in the `home_value_source` column of the annual CSVs; `zillow_from` gives the first Zillow year.
- **Cities:** Zillow only, so 2000 onward. 8,940 cities have a value for 2000; the rest start later.

Other fields:

| Field | What it is | Coverage |
|---|---|---|
| `rent` | Zillow's typical rent (ZORI) | 2015+ |
| `fmr_2br` | HUD's two-bedroom Fair Market Rent | counties, 1983+ |
| `median_income` | Census CPS median household income | states, 1984+ |
| `value_to_income` | `home_value` ÷ `median_income`, an affordability measure | states |
| `rpp_all`, `rpp_housing` | BEA cost-of-living index (US = 100); compares states within a year, not across years | states |
| `acs_*` | Census ACS 1-year estimates | states |
| `census_*` | Census ACS 5-year estimates, labelled by end year, plus the 2000 census if you downloaded with a key | counties, cities |
| `census_decennial_*` | Census median value and rent, every 10 years | states, 1940–2000 |

**City locations (`match`):**

| Value | Meaning | Cities |
|---|---|---|
| `place` / `place_alias` | Census place point | 18,235 |
| `cousub` | township or town (NJ, PA, MI, New England) | 1,358 |
| `override` | hand-fixed in `scripts/city_overrides.csv` | 17 |
| `county` | Zillow's county center point, so the location is approximate | 1,757 |

The 1,757 `county` matches are mostly small postal-only towns. Filter on `match != "county"` if exact positions matter.

To convert to inflation-adjusted dollars of a given year: `value * cpi[year_target] / cpi[year]`.

**Attribution required on any published visualization:** Zillow (ZHVI/ZORI), plus FHFA, U.S. Census Bureau, BEA and HUD where those fields are used.
