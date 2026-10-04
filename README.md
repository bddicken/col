# US Housing Costs (col)

This project shows the cost of housing in the United States on a 3D map. The map shows states, counties, and cities from 1975 to 2026.

The project has two parts:

- A data pipeline in `scripts/`. The pipeline downloads public data and makes the files that the app uses.
- A web app in `app/`. The app shows the data on a 3D map.

The repository does not include the data. To make the data, do procedures 1 to 3. To start the app, do procedure 4. To publish the app on Cloudflare, do procedure 5. To publish the app automatically after each push to `main`, do procedure 6.

The live app is at https://col.bendicken.workers.dev.

For information about each data source and its terms of use, refer to [DATA_SOURCES.md](DATA_SOURCES.md).

## Requirements

| Item | Requirement |
|---|---|
| Python | Version 3.9 or later |
| Node.js | Version 20.19 or later, or version 22.12 or later |
| Disk space | Approximately 300 MB |
| Network | An internet connection for the download |

## Procedure 1: Set up the Python environment

1. Go to the root directory of the repository.
2. Make a virtual environment:

   ```bash
   python3 -m venv .venv
   ```

3. Install the Python packages:

   ```bash
   .venv/bin/pip install -r requirements.txt
   ```

## Procedure 2: Download the data

1. Run the download script:

   ```bash
   .venv/bin/python scripts/download.py
   ```

2. Make sure that the last line of the output is `done`.
3. If the last line is `done, with failures (re-run to retry)`, do step 1 again. The script downloads only the files that are missing.

The script writes approximately 220 MB to `data/raw/`. Each data source has its own directory.

> **NOTE:** The script does not download a file again if the file is already in `data/raw/`. To download all the files again, use the `--force` option.

### Download options

| Option | Function |
|---|---|
| `--only SOURCES` | Downloads only the given sources. Use commas between the sources, for example `--only zillow,fred`. The sources are `zillow`, `fhfa`, `census`, `bea`, `hud`, `fred`, and `geo`. |
| `--force` | Downloads all the files again, also the files that are already in `data/raw/`. |
| `--large` | Also downloads the Zillow ZIP-code files. Each file is approximately 125 MB. The app does not use these files. |

### Optional: Download the Census history

Without a Census API key, the Census data for counties and cities starts in 2021. With a key, the script also downloads:

- Census data (ACS) for states from 2005.
- Census data (ACS) for counties and cities from 2009.
- 2000 census data for counties and cities.

To download the Census history:

1. Request a free key at https://api.census.gov/data/key_signup.html.
2. Open the email from the Census Bureau. Click the activation link in the email.

   > **NOTE:** The key does not operate until you activate it.

3. Run the download script with the key. Replace `YOUR_KEY` with your key:

   ```bash
   CENSUS_API_KEY=YOUR_KEY .venv/bin/python scripts/download.py --only census
   ```

4. Make sure that the output does not show `FAIL` lines.
5. If the output shows `Census API rejected the key`, activate the key. Then do step 3 again.

The project does not keep the key in a file. Give the key only in the command.

## Procedure 3: Process the data

1. Run the process script:

   ```bash
   .venv/bin/python scripts/process.py
   ```

2. Make sure that the output does not show an error.

The script reads the files in `data/raw/`. It writes the processed files to `data/processed/`. It also copies the files that the app loads to `data/processed/web/`. The script takes less than 1 minute.

To process only some of the data, give the names of the steps. For example:

```bash
.venv/bin/python scripts/process.py states counties
```

The steps are `states`, `counties`, `cities`, and `by_state`. The `by_state` step uses the output of the other three steps.

## Procedure 4: Start the app

> **NOTE:** The app reads the files in `data/processed/web/`. Do procedures 1 to 3 before you start the app.

1. Go to the `app` directory:

   ```bash
   cd app
   ```

2. Install the packages:

   ```bash
   npm install
   ```

3. Start the development server:

   ```bash
   npm run dev
   ```

4. Open http://localhost:5173 in a web browser.

## Procedure 5: Deploy the app to Cloudflare

The app is a static site on Cloudflare Workers. The deployment includes the app and the files in `data/processed/web/` (approximately 11 MB). It does not include the other files in `data/processed/`.

1. Do procedures 1 to 3.
2. Go to the `app` directory:

   ```bash
   cd app
   ```

3. Install the packages:

   ```bash
   npm install
   ```

4. Log in to Cloudflare. A web browser opens. Log in and give access to Wrangler:

   ```bash
   npx wrangler login
   ```

   > **NOTE:** You must do this step only one time on each computer.

5. Build and deploy the app:

   ```bash
   npm run deploy
   ```

6. Make sure that the output shows `Deployed col triggers` and the URL of the app.

The settings for the deployment are in `app/wrangler.jsonc`. The name of the app is `col`.

## Procedure 6: Set up automatic deployment

The GitHub workflow `.github/workflows/deploy.yml` deploys the app after each push or merge to `main`. The workflow downloads the data, processes it, builds the app, and deploys it to Cloudflare. The workflow keeps the downloaded files for one calendar month. Thus, the first run of each month downloads new data.

The workflow needs a Cloudflare API token. You must do these steps only one time.

1. Open https://dash.cloudflare.com/profile/api-tokens.
2. Click **Create Token**.
3. Find the **Edit Cloudflare Workers** template. Click **Use template**.
4. In **Account Resources**, select your account.
5. In **Zone Resources**, select **All zones**.
6. Click **Continue to summary**. Then click **Create Token**.
7. Copy the token.
8. Add the token to the GitHub repository as a secret. When the command asks for the value, paste the token:

   ```bash
   gh secret set CLOUDFLARE_API_TOKEN --repo bddicken/col
   ```

9. Start the workflow:

   ```bash
   gh workflow run deploy.yml --repo bddicken/col
   ```

10. Make sure that the workflow completes without errors:

    ```bash
    gh run watch --repo bddicken/col
    ```

The workflow also uses the repository variable `CLOUDFLARE_ACCOUNT_ID`. This variable is already set.

## Update the data

Zillow and FRED publish new data each month. FHFA publishes new data each quarter. To update the data:

1. Download all the files again:

   ```bash
   .venv/bin/python scripts/download.py --force
   ```

2. Process the data:

   ```bash
   .venv/bin/python scripts/process.py
   ```

3. If the app is open, reload the page in the web browser.
4. To update the live app, do steps 2 and 5 of procedure 5. If you did procedure 6, the workflow downloads new data in the first run of each month.

## Use the app

### The US map

The height and the color of each state show the value of the selected measure. Green is a low value. Red is a high value.

- To turn the map, drag it.
- To zoom, scroll.
- To show the value of a state, put the pointer on the state.

### The measures

Select a measure at the top of the page.

| Measure | Description | Available for |
|---|---|---|
| Home value | The typical home value, adjusted for inflation to 2026 dollars | States, counties, cities |
| Home value (nominal) | The typical home value, in the dollars of each year | States, counties, cities |
| Price-to-income | The home value divided by the median household income | States |
| Cost of living | The BEA price index. The US value is 100. | States |

### The scale

The legend in the top-left corner shows the scale. The **Scale** control changes the scale:

- **All years**: The scale includes the values of all years. Use this setting to compare years.
- **This year**: The scale includes only the values of the selected year. Use this setting to compare places in one year.

### The timeline

The line chart at the bottom shows the trend for the US, or for the selected state.

- To select a year, click the chart.
- To move through the years, drag on the chart.
- To play all the years, press the Space bar. To stop, press the Space bar again.

### The state view

1. To show a state, click the state on the map or in the list.
2. To show counties, click **Counties**. To show cities, click **Cities**.
3. To show the history of a county or a city, click it on the map or in the list.
4. To go back to the US map, do one of these steps:
   - Click outside the state.
   - Press Esc.
   - Click **US Housing Costs** at the top of the page.

In the state view, labels show the 8 cities with the largest population. The address in the browser shows the view, for example `#CA` or `#CA/cities`.

## Directory layout

```
data/
  raw/                  Source files, one directory for each source (not in the repository)
  processed/            Processed files (not in the repository)
    web/                The files that the app loads. Only this directory is deployed.
scripts/
  download.py           Downloads the source files
  process.py            Runs all the processing steps
  build_states.py       Makes the state files
  build_counties.py     Makes the county files
  build_cities.py       Makes the city files and finds the location of each city
  build_state_files.py  Makes one file for each state, for the state view
  city_overrides.csv    Manual city locations
  common.py             Shared functions
.github/workflows/
  deploy.yml            Deploys the app after each push to main
app/
  index.html            The app page
  src/                  The app code
  wrangler.jsonc        The Cloudflare settings
```

## Processed data

The process script writes these files to `data/processed/`:

| File | Contents | Years |
|---|---|---|
| `states.json` | 50 states, DC, and the US total | 1975 to 2026. Monthly values from January 2000. |
| `states_annual.csv` | The state data, with one row for each state and year | 1975 to 2026 |
| `states_monthly.csv` | The monthly Zillow values for each state | January 2000 to the latest month |
| `counties.json` | 3,142 counties. 3,071 counties have home values. | 1975 to 2027 |
| `counties_annual.csv` | The county data, with one row for each county and year | 1975 to 2027 |
| `cities.json` | 21,367 cities with a location | 2000 to 2026 |
| `cities_annual.csv` | The city data, with one row for each city and year | 2000 to 2026 |
| `city_crosswalk.csv` | The location of each Zillow city, and how the script found it | Not applicable |
| `web/` | The files that the app loads: `states.json`, `by_state/{fips}.json`, and the map shapes | Not applicable |
| `web/by_state/{fips}.json` | The counties and cities of one state. The app loads this file when you open a state. | 1975 to 2026 |
| `cpi.json` | The consumer price index (CPI-U), annual average | 1947 to 2026 |
| `geo/*.json` | The map shapes of the states and counties (TopoJSON) | Not applicable |

Rules for all the files:

- All money values are in the dollars of each year (nominal dollars).
- Each JSON file has a `meta` object that describes the fields.
- Each value list in a JSON file has one value for each year in the `years` list of that file.
- `null` shows that no data is available.
- The value for the latest year is the average of the months that are available. The `meta.partial_year` field gives the number of months.

To adjust a value for inflation, use this formula:

```
value in target year dollars = value × cpi[target year] ÷ cpi[year]
```

### Fields

| Field | Description | Available for |
|---|---|---|
| `home_value` | The typical home value. Refer to "How the scripts calculate home values". | States, counties, cities |
| `rent` | The typical rent from Zillow (ZORI), from 2015 | Counties, cities |
| `fmr_2br` | The HUD Fair Market Rent for two bedrooms, from 1983 | Counties |
| `median_income` | The median household income from the Census CPS survey, from 1984 | States |
| `value_to_income` | `home_value` divided by `median_income` | States |
| `rpp_all`, `rpp_housing` | The BEA price indexes (US = 100). Compare these values only in one year. | States |
| `acs_*` | Census ACS 1-year values | States |
| `census_*` | Census ACS 5-year values, and 2000 census values if you used a Census API key | Counties, cities |
| `census_decennial_*` | The Census median home value and rent, every 10 years from 1940 to 2000 | States |

## How the scripts calculate home values

**States and counties, from 2000:** The value is the Zillow Home Value Index (ZHVI). The script calculates the average of the 12 months of each year.

**States and counties, before 2000:** Zillow data starts in 2000. For earlier years, the script uses the FHFA house price index:

1. The script scales the index to the first Zillow value.
2. The script adjusts the result to agree with the census median values for 1980 and 1990.

For counties, the script uses the FHFA county index. If the county index is not available, the script uses the state index. The `home_value_source` column in the CSV files shows the source for each year.

**Cities:** The value is the Zillow value only. City values start in 2000. Approximately 8,900 cities have a value for 2000.

**City locations:** The Zillow files do not give the location of a city. The script finds each city in the Census Gazetteer by its name and state. The `match` field shows how the script found the location:

| `match` | Location | Cities |
|---|---|---|
| `place`, `place_alias` | A Census place | 18,235 |
| `cousub` | A township or a town | 1,358 |
| `override` | A manual location from `scripts/city_overrides.csv` | 17 |
| `county` | The center of the county. This location is approximate. | 1,757 |

The app does not show cities with the `county` match.

To correct the location of a city, add a line to `scripts/city_overrides.csv`. Then do procedure 3 again.

## Troubleshooting

| Problem | Possible cause | Action |
|---|---|---|
| The download output shows `FAIL` lines. | A server did not respond. | Run the download script again. |
| The output shows `Census API rejected the key`. | The key is not active. | Click the activation link in the email from the Census Bureau. Run the script again. |
| The process script stops with `No such file or directory`. | A source file is missing. | Do procedure 2 again. |
| The app does not show the map. | The files in `data/processed/web/` are missing. | Do procedures 2 and 3. Then reload the page. |
| `npm run deploy` shows an authentication error. | Wrangler is not logged in to Cloudflare. | Do step 4 of procedure 5. |
| The GitHub workflow stops with `The CLOUDFLARE_API_TOKEN secret is not set`. | The repository does not have the token. | Do procedure 6. |

## Attribution

If you publish the map or the data, show the data sources: Zillow, FHFA, U.S. Census Bureau, BEA, BLS, and HUD. Zillow requires clear attribution. For the terms of each source, refer to [DATA_SOURCES.md](DATA_SOURCES.md).
