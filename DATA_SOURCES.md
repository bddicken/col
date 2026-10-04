# US Housing Cost Data — Source Research

Researched 2026-10-03. URLs marked ✓ were checked live (HTTP 200 and/or file parsed) on that date.

## TL;DR

| Need | Best source | Geography | History | Unit |
|---|---|---|---|---|
| **Primary home values** | Zillow ZHVI | State, metro, county, **city (~21k)**, ZIP | **2000-01 → 2026-08**, monthly | $ (typical home value) |
| Pre-2000 history / validation | FHFA HPI (all-transactions) | State, metro, county, ZIP | **1975 → 2026Q2** | Index (convert via anchor) |
| Long-run state anchors | Census Historical Census of Housing | State | **1940 → 2000**, decennial | $ median value |
| Official city medians | Census ACS 5-year `B25077` | All Census places (~30k) | 2009 → 2024, annual | $ median value |
| Rents | Zillow ZORI / ACS `B25064` / HUD FMR | City / place / county | 2015+ / 2009+ / **1983+** | $ |
| Overall cost of living | BEA Regional Price Parities | State, metro (no cities) | 2008 → 2024, annual | Index (US = 100) |
| City coordinates | Census Gazetteer (places) | 32k places, lat/long | current | — |
| State polygons | Census Cartographic Boundary 20m / `us-atlas` | State, county | current | — |

**Recommendation:** build on **Zillow ZHVI State + City** (dollar values, both levels, 26+ years, free with attribution). If you want history back past 2000, extend states with **FHFA HPI** scaled to Zillow's Jan-2000 dollar level. If the "cost of living" layer should mean more than housing, add **BEA RPP**.

---

## 1. Zillow Research — ZHVI (primary)

- ✓ URL pattern: `https://files.zillowstatic.com/research/public_csvs/zhvi/{Geo}_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv`
  - `Geo` is one of `State`, `Metro`, `County`, `City`, `Zip` or `Neighborhood`.
  - Files are updated monthly. Last modified 2026-09-16.
  - Sizes: State 0.3 MB, City 94 MB, Zip 124 MB.
  - Bedroom-count variants exist, e.g. `City_zhvi_bdrmcnt_3_uc_sfrcondo_...`.
- ✓ Format: wide CSV with one row per region and one column per month-end.
  - City columns: `RegionID, SizeRank, RegionName, RegionType, StateName, State, Metro, CountyName, 2000-01-31 … 2026-08-31`
- ✓ Coverage:
  - State: 51 rows (50 states + DC).
  - City: 21,369 cities. All have a current value, but only **8,691 have a value back to Jan 2000**, so the city history is sparse in early years.
- ✓ Rents (ZORI): `.../zori/{City|Metro|County|Zip}_zori_uc_sfrcondomfr_sm_month.csv`
  - Starts 2015-01, ~4,500 cities.
  - There is no state-level ZORI file.
- **No lat/long or FIPS codes in the files.** See §5 for how to join them to the map.
- **Terms:** free for public use with "proper and clear attribution" to Zillow. Check the Terms of Use before redistributing the raw CSVs, and display "Data: Zillow" on the visualization.
- No data before 2000.

## 2. FHFA House Price Index (extends history to 1975)

- ✓ Master file: `https://www.fhfa.gov/hpi/download/monthly/hpi_master.csv`
  - 17 MB, long format.
  - Columns: `hpi_type, hpi_flavor, frequency, level, place_name, place_id, yr, period, index_nsa, index_sa`
- ✓ Quarterly state file: `https://www.fhfa.gov/hpi/download/quarterly_datasets/hpi_at_state.csv`
  - No header row; columns are state, year, quarter, index.
  - Covers 1975Q1 → 2026Q2.
- ✓ Annual files with base-2000 = 100 versions: `https://www.fhfa.gov/hpi/download/annual/hpi_at_{state,cbsa,county,zip3,zip5}.xlsx`
- No city/place level.
- Only covers conforming (Fannie/Freddie) loans.
- It is a repeat-sales **index**. Convert it to dollars with an anchor:
  `value(t) = Zillow_or_Census_median(anchor_year) × HPI(t) / HPI(anchor_year)`
- Public domain.
- Alternative with similar coverage: **Freddie Mac FMHPI**, monthly by state and CBSA, 1975-01 → 2026-08.
  - ✓ `https://www.freddiemac.com/fmac-resources/research/docs/fmhpi_master_file.csv`

## 3. Census Bureau (official dollar medians, public domain)

> ⚠️ **As of May 2026, the Census Data API requires a free key for every data query** (keyless calls redirect to an error). Get one at census.gov/data/developers. Alternatively, use the keyless summary-file downloads below.
>
> ⚠️ **The 2025 ACS 1-year release is delayed indefinitely.** The latest available data is ACS 1-year 2024 and ACS 5-year 2020–2024.

- **ACS tables:**
  - `B25077` median home value
  - `B25064` median gross rent
  - `B19013` median household income, for affordability ratios
- **ACS 1-year:**
  - Available 2005–2019 and 2021–2024; the standard 2020 release was never published.
  - Places with 65k+ population only (657 places in 2024).
- **ACS 5-year:**
  - Available 2009–2024.
  - Covers **all places**, counties, tracts and ZCTAs.
  - Overlapping 5-year windows shouldn't be compared year over year.
- API: `https://api.census.gov/data/2024/acs/acs5?get=NAME,B25077_001E&for=place:*&in=state:*&key=KEY`
- ✓ Keyless bulk download: `https://www2.census.gov/programs-surveys/acs/summary_file/2024/table-based-SF/data/1YRData/acsdt1y2024-b25077.dat`
  - Pipe-delimited. Replace `1YRData`/`acsdt1y` with `5YRData`/`acsdt5y` for the 5-year file.
- **Decennial 2000:** SF3 `H085001` is median value by place (API `.../data/2000/dec/sf3`). 1990 isn't in the API; get it from NHGIS (free account).
- **2010 and 2020 decennial censuses don't ask about home value.** ACS replaced the long form.
- ✓ **Historical Census of Housing, by state, 1940–2000:**
  - `https://www2.census.gov/programs-surveys/decennial/tables/time-series/coh-values/values-unadj.txt`
  - `-adj.txt` is the inflation-adjusted version.
  - Gross rents are in `coh-grossrents/`.

## 4. Other sources

| Source | Notes |
|---|---|
| **BEA Regional Price Parities** | ✓ `https://apps.bea.gov/regional/zip/SARPP.zip` (state) and `MARPP.zip` (metro, 393 areas). Annual 2008–2024.<br>Line 1 = all items, line 3 = housing.<br>This is the real "cost of living" measure. It compares areas within a year, not across years. Public domain. |
| **HUD Fair Market Rents** | ✓ `https://www.huduser.gov/portal/datasets/FMR/FMR_2Bed_1983_2027.csv`. County level, FY1983–FY2027.<br>Policy rent (about the 40th percentile), not a market median.<br>Downloads need a browser user agent and `--compressed`. |
| **Redfin Data Center** | Median **sale** price. State, metro, county, city, ZIP, starting **2012** (too short for this project's history).<br>Old `redfin_market_tracker/*.tsv000.gz` files were frozen in June 2026. New ones are at `https://redfin-public-data.s3.us-west-2.amazonaws.com/redfin_data_center/property_types/monthly/all_{states,cities,...}.csv` (the city file is 2.2 GB).<br>Useful as a cross-check. |
| **Realtor.com** | **Listing** prices. State, metro, county, ZIP (no city), starting 2016-07. Attribution required. |
| **Case-Shiller** | Index for 20 metros + national, from 1987, via FRED. Reproduction prohibited without S&P permission, so use it for personal checks only. |
| **NAR metro medians** | History file costs $1,500, with redistribution restrictions. Skip it. |
| **FRED** | Aggregator. Keyless CSV: `https://fred.stlouisfed.org/graph/fredgraph.csv?id=SERIES`<br>State HPI is `{ST}STHPI`, e.g. `CASTHPI`. State median income is `MEHOINUS{ST}A646N`. |

## 5. Geography & joining

- **City points:** ✓ Census Gazetteer `https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2025_Gazetteer/2025_Gaz_place_national.zip`
  - Pipe-delimited, 32,350 places.
  - Columns include `GEOID, NAME, INTPTLAT, INTPTLONG, ALAND`.
  - No population column; join ACS `B01003` on GEOID if you need it.
- **Polygons:**
  - ✓ Cartographic Boundary files: `https://www2.census.gov/geo/tiger/GENZ2025/shp/cb_2025_us_{state|county|cbsa}_20m.zip`. Places are only available at `500k`.
  - ✓ Ready-made TopoJSON: `us-atlas@3` (`states-10m.json`, `counties-10m.json`, and pre-projected `*-albers-10m.json`).
    - It has no cities.
    - It's built from 2017 boundaries, so Connecticut counties won't match data from 2022 on, when Connecticut switched to planning regions.
- **Zillow city → Census place join (main data-engineering task):**
  - There's no published crosswalk.
  - Zillow "cities" follow mailing-address names, not legal boundaries.
  - A naive match on (state, name without its "city"/"CDP" suffix) linked **84.8%** of Zillow cities to the Gazetteer, but **31 of the top 1,000 failed**. Causes:
    - Consolidated governments, e.g. Gazetteer names Nashville "Nashville-Davidson metropolitan government (balance)".
    - Renames, e.g. "Urban Honolulu", and Ventura is "San Buenaventura".
    - NJ/MI/PA townships, which are county subdivisions rather than places.
    - Punctuation, e.g. Lees Summit / Lee's Summit.
  - Plan: normalized name match, then a manual override table for the largest ~500, then a fallback to the county-subdivision Gazetteer file.
- **Definitional pitfalls:**
  - "City" means different things: a Census place, a Zillow postal city, and a metro (CBSA) are all different units.
  - CBSA definitions changed in 2013, 2018, 2020 and 2023.
  - Places annex land every year.
  - For consistent 25-year comparisons, states (and counties on one fixed vintage) are the stable units. Treat city points as locations, not fixed areas.

## 6. Notes for the visualization

- **Dollars are nominal.** For a 30-year comparison, deflate with CPI (FRED `CPIAUCSL`). Or show price ÷ median income (affordability), which adjusts itself.
- **Height map:**
  - States: extruded polygons (deck.gl `GeoJsonLayer` with `extruded`, or MapLibre `fill-extrusion`).
  - Cities: one column per city point (deck.gl `ColumnLayer`), with height = ZHVI.
- **Interpolating city points into a continuous surface is misleading.** Prices jump at metro edges and coastlines, and rural areas would get made-up values. If you do it anyway, mask it to populated areas and label it illustrative. A county-level choropleth or extrusion is a more honest continuous-looking layer.
