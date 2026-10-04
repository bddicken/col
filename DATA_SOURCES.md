# Data sources

This document lists the data sources of the project. For each source, it gives the data, the URLs, the coverage, and the terms of use.

The information is correct on 3 October 2026. The download script (`scripts/download.py`) uses the URLs in this document.

## Summary

| Source | Data | Geography | Years | Unit |
|---|---|---|---|---|
| Zillow ZHVI | Typical home value | State, metro, county, city | 2000 to 2026, monthly | Dollars |
| Zillow ZORI | Typical rent | Metro, county, city | 2015 to 2026, monthly | Dollars |
| FHFA HPI | House price index | US, state, metro, county | 1975 to 2026 | Index |
| Census Historical Census of Housing | Median home value and rent | US, state | 1940 to 2000, every 10 years | Dollars |
| Census ACS | Median home value, rent, income, and population | US, state, county, city | 2005 to 2024, annual | Dollars, persons |
| Census 2000 SF3 | Median home value, rent, income, and population | State, county, city | 2000 | Dollars, persons |
| BEA Regional Price Parities | Cost-of-living index | State, metro | 2008 to 2024, annual | Index (US = 100) |
| HUD Fair Market Rents | Rent for 0 to 4 bedrooms | County | 1983 to 2027, annual | Dollars |
| FRED | CPI-U and median household income | US, state | 1947 to 2026 | Index, dollars |
| Census Gazetteer | Location of places, county subdivisions, and counties | Place, county | 2025 | Latitude and longitude |
| us-atlas | Map shapes of the states and counties | State, county | 2017 boundaries | TopoJSON |

## Zillow

### Zillow Home Value Index (ZHVI)

The ZHVI is the typical value of a home in an area. It is in dollars. The project uses the version for all homes (single-family and condominium) in the middle price tier, adjusted for the season.

- **URL:** `https://files.zillowstatic.com/research/public_csvs/zhvi/{Geo}_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv`
- **`{Geo}` values that the project uses:** `State`, `Metro`, `County`, `City`. The `--large` option also downloads `Zip`.
- **Format:** CSV. Each row is one area. Each month is one column.
- **Coverage:** 51 states (with DC), 3,071 counties, and 21,369 cities. Only 8,691 cities have a value for January 2000.
- **Update:** Each month.

The files do not give a latitude, a longitude, or a Census code for a city. The script `build_cities.py` finds these values in the Census Gazetteer.

### Zillow Observed Rent Index (ZORI)

The ZORI is the typical rent in an area. It is in dollars for each month.

- **URL:** `https://files.zillowstatic.com/research/public_csvs/zori/{Geo}_zori_uc_sfrcondomfr_sm_month.csv`
- **`{Geo}` values that the project uses:** `Metro`, `County`, `City`.
- **Coverage:** From January 2015. Approximately 4,500 cities. Zillow does not publish a state file.

### Terms of use

Zillow permits public use of the data. Zillow requires clear attribution, for example "Data: Zillow". Read the Zillow Terms of Use before you publish the source files or files that you make from them.

## Federal Housing Finance Agency (FHFA)

The FHFA House Price Index (HPI) measures the change in price of the same homes over time. The index is not in dollars. The project uses the index to calculate home values before 2000.

| File | URL | Contents |
|---|---|---|
| Master file | `https://www.fhfa.gov/hpi/download/monthly/hpi_master.csv` | US, state, and metro indexes. Quarterly from 1975. |
| County file | `https://www.fhfa.gov/hpi/download/annual/hpi_at_county.xlsx` | County indexes. Annual from 1975 to 2025. |

Limits of the FHFA data:

- The index includes only homes with loans from Fannie Mae or Freddie Mac.
- Some counties have no data in the early years.
- The county file uses the 2022 planning regions for Connecticut. The project uses the state index for Connecticut counties.

**Terms of use:** Public domain.

## U.S. Census Bureau

### Historical Census of Housing

These tables give the median home value and the median rent for each state.

- **Home values:** `https://www2.census.gov/programs-surveys/decennial/tables/time-series/coh-values/values-unadj.txt`
- **Rents:** `https://www2.census.gov/programs-surveys/decennial/tables/time-series/coh-grossrents/grossrents-unadj.txt`
- **Coverage:** Each census from 1940 to 2000.
- **Format:** Text with fixed columns. The `-adj.txt` versions are adjusted for inflation.

The project uses the 1980 and 1990 values to adjust the home values before 2000.

### American Community Survey (ACS)

The ACS gives medians for each year. The project uses these tables:

| Table | Data |
|---|---|
| B25077 | Median home value |
| B25064 | Median gross rent |
| B19013 | Median household income |
| B01003 | Total population |

The ACS has two versions:

- **1-year:** Areas with 65,000 or more persons. The project uses this version for states.
- **5-year:** All areas. The project uses this version for counties and cities. The year is the last year of the 5 years.

The project downloads the ACS data in two ways:

| Method | Years | Key | URL |
|---|---|---|---|
| Summary files | 2021 to 2024 | Not necessary | `https://www2.census.gov/programs-surveys/acs/summary_file/{year}/table-based-SF/data/{1YRData or 5YRData}/acsdt{1 or 5}y{year}-{table}.dat` |
| Census API | 1-year: 2005 to 2024. 5-year: 2009 to 2024. | Necessary | `https://api.census.gov/data/{year}/acs/{acs1 or acs5}` |

The download script keeps only the US, state, county, and place rows of the summary files.

Limits of the ACS data:

- The Census Bureau did not publish the standard 1-year data for 2020.
- The 2025 1-year data is late. The Census Bureau did not give a date.
- Do not compare 5-year values for years next to each other. The two periods have 4 years in common.

### 2000 census (SF3)

The 2000 census is the last census with home values. The 2010 and 2020 censuses do not ask about home value.

- **URL:** `https://api.census.gov/data/2000/dec/sf3`
- **Variables:** `H085001` (median home value), `H063001` (median gross rent), `P053001` (median household income in 1999), `P001001` (population).
- **Key:** Necessary.

### Census API key

Since May 2026, the Census API requires a key for all data requests. The key is free. To request a key, go to https://api.census.gov/data/key_signup.html. For the procedure, refer to the README.

### Census Gazetteer

The Gazetteer gives the location (latitude and longitude) and the land area of each Census area.

- **URL:** `https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2025_Gazetteer/2025_Gaz_{layer}_national.zip`
- **`{layer}` values that the project uses:** `place`, `cousubs`, `counties`, `cbsa`, `state`.
- **Format:** Text with `|` between the columns.

The 2025 Gazetteer uses the planning regions for Connecticut. It does not include the old Connecticut counties.

**Terms of use for all Census data:** Public domain.

## Bureau of Economic Analysis (BEA)

The Regional Price Parities (RPP) compare the cost of living between areas. The US value is 100.

- **States:** `https://apps.bea.gov/regional/zip/SARPP.zip`
- **Metro areas:** `https://apps.bea.gov/regional/zip/MARPP.zip`
- **Coverage:** Annual, 2008 to 2024.
- **Lines that the project uses:** Line 1 (all items) and line 3 (housing).

Compare RPP values only in one year. The RPP does not show the change over time.

**Terms of use:** Public domain.

## Department of Housing and Urban Development (HUD)

The Fair Market Rent (FMR) is the rent that HUD uses for housing programs. It is approximately the 40th percentile of rents. It is not a market median.

- **URL:** `https://www.huduser.gov/portal/datasets/FMR/FMR_All_1983_2027.csv`
- **Coverage:** Counties, fiscal years 1983 to 2027, for 0 to 4 bedrooms.

The HUD server sends a web page instead of the file to most scripts. To receive the file, the download script identifies itself as a web browser. It does this only for the HUD server.

In New England, HUD gives the FMR for each town. The project uses the median of the towns in each county.

**Terms of use:** Public domain.

## FRED (Federal Reserve Bank of St. Louis)

FRED gives data from other agencies in one place. The project uses these series:

| Series | Data | Source agency | Years |
|---|---|---|---|
| `CPIAUCSL` | Consumer price index (CPI-U) | BLS | 1947 to 2026 |
| `MEHOINUSA646N` | US median household income | Census Bureau (CPS) | 1984 to 2025 |
| `MEHOINUS{ST}A646N` | State median household income. `{ST}` is the state code, for example `CA`. | Census Bureau (CPS) | 1984 to 2025 |

- **URL:** `https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}`
- **Key:** Not necessary for this URL.

**Terms of use:** The terms of the source agency apply. These series are public domain.

## us-atlas

us-atlas gives the map shapes of the US states and counties in TopoJSON format. The shapes come from the 2017 Census cartographic boundary files.

- **URL:** `https://cdn.jsdelivr.net/npm/us-atlas@3/{file}`
- **Files that the project uses:** `states-10m.json`, `counties-10m.json`, `nation-10m.json`, and the `-albers-` versions of these files.
- **Albers versions:** The shapes are projected to a 975 × 610 area. Alaska and Hawaii are below the other states.

The county shapes use the old Connecticut counties. Zillow also uses the old counties.

**Terms of use:** ISC license.

## Sources that the project does not use

| Source | Data | Reason |
|---|---|---|
| Redfin Data Center | Median sale price | The data starts in 2012. |
| Realtor.com | Median listing price | The data starts in 2016. It has no city data. |
| S&P CoreLogic Case-Shiller | House price index for 20 metro areas | It has no state or city data. S&P does not permit publication without approval. |
| NAR metro medians | Median sale price | The historical file costs $1,500. NAR does not permit publication without approval. |
| Freddie Mac FMHPI | House price index | FHFA gives similar data in the public domain. |

## Limits of the data

- **Cities:** A Zillow city uses the city name of a mailing address. It is not the same as a Census place. The project finds the nearest match. Refer to the README for the method.
- **Metro areas:** The Census Bureau changed the metro area definitions in 2013, 2018, 2020, and 2023. Zillow uses the 2013 definitions.
- **City areas:** Cities change their boundaries over time. Use a city point as a location, not as a fixed area.
- **Dollars:** All source values are in the dollars of each year. To compare years, adjust the values for inflation with the CPI.
