# snow-detection

Expedition snow and weather analysis for a high-altitude site in the Pir Panjal / Bara Bhangal region of Himachal Pradesh (33.04917°N, 76.83113°E, ~4,565 m). Pulls free satellite imagery and weather-model data, computes snow metrics, and renders a pre-expedition report.

**Latest generated report: [`output/REPORT.md`](output/REPORT.md)**

## What it produces

- **Snow depth, snowfall, temperature, freezing level, wind** — hourly for the last 7 days (+3-day forecast) and daily for the last 30 days, from the [Open-Meteo](https://open-meteo.com/) API (ERA5 reanalysis + forecast model; free, no API key).
- **Snow cover maps** — every Sentinel-2 pass over the site in the last month (10 m resolution, the best free imagery available), fetched from the [Earth Search](https://earth-search.aws.element84.com/v1) STAC API on AWS (free, no auth). Only a 10×10 km window is downloaded per scene thanks to COG range requests.
- **Snow-covered %** of the area per scene via NDSI = (green − SWIR)/(green + SWIR) with per-pixel cloud masking (Sentinel-2 scene classification layer).
- **Snowline elevation** per scene — NDSI crossed with the Copernicus GLO-30 DEM; the snowline is the lowest 100 m elevation band that is ≥50% snow-covered.
- **`output/REPORT.md`** — everything combined: current snow state, trend charts, satellite imagery, and plain-language notes for the expedition (fresh-snow/avalanche signal, freezing level vs site elevation, melt-out rate).

## Setup

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Usage

Run the full chain (each step writes to `output/`):

```sh
.venv/bin/python fetch_weather.py    # Open-Meteo → CSVs
.venv/bin/python fetch_satellite.py  # Sentinel-2 scenes + DEM → GeoTIFFs
.venv/bin/python analyze_snow.py     # NDSI snow cover + snowline → CSVs
.venv/bin/python make_report.py      # plots, maps, REPORT.md
```

Re-run any day to pick up the newest satellite pass and forecast. Already-downloaded scenes are cached in `output/rasters/`.

## Configuration

Everything site-specific lives in `config.py` — change `LAT`/`LON` to analyze a different location, `AOI_HALF_KM` for the analysis box size, and `DAYS_MONTH`/`DAYS_RECENT` for the time windows.

## Notes on the data

- Open-Meteo is a ~9 km model grid downscaled to the point — treat absolute snow depth as indicative, trends as reliable.
- Satellite snow extent is directly observed and is the trustworthy "where is the snow" signal; cloudy passes contribute fewer valid pixels and are flagged in the report rather than dropped.
- Commercial sub-meter imagery (Maxar, Planet) exists but is not free; Sentinel-2 at 10 m is the practical ceiling for a free pipeline.
