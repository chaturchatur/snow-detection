"""Fetch Sentinel-2 L2A imagery and Copernicus DEM over the AOI.

Searches Earth Search (free, no auth) for the past DAYS_MONTH days, picks the
lowest-cloud scenes plus the most recent scene, and saves AOI-windowed GeoTIFFs
for the green band (B03), SWIR band (B11), scene classification (SCL), the
true-color visual, and the DEM. COG range requests mean only the AOI window is
downloaded, not full 100x100 km tiles.

Produces:
  output/rasters/<date>_<band>.tif
  output/rasters/dem.tif
  output/data/scenes.csv
"""
import datetime as dt
import os

# The Copernicus DEM bucket is public but only accepts unsigned requests
os.environ["AWS_NO_SIGN_REQUEST"] = "YES"

import pandas as pd
import rioxarray
from pystac_client import Client

from config import (
    STAC_URL, LAT, LON, DAYS_MONTH, MAX_CLEAR_SCENES, SCENE_CLOUD_LIMIT,
    aoi_bbox, RASTER_DIR, DATA_DIR,
)

BANDS = {"green": "B03", "swir16": "B11", "scl": "SCL", "visual": "RGB"}


def search_scenes(client):
    end = dt.datetime.now(dt.timezone.utc)
    start = end - dt.timedelta(days=DAYS_MONTH)
    search = client.search(
        collections=["sentinel-2-l2a"],
        bbox=aoi_bbox(),
        datetime=f"{start.isoformat()}/{end.isoformat()}",
        limit=100,
    )
    items = list(search.items())
    # One item per day (adjacent tiles can both cover the AOI); keep the less cloudy
    by_date = {}
    for it in items:
        date = it.datetime.date()
        prev = by_date.get(date)
        if prev is None or it.properties["eo:cloud_cover"] < prev.properties["eo:cloud_cover"]:
            by_date[date] = it
    return sorted(by_date.values(), key=lambda it: it.datetime)


def select_scenes(items):
    clear = [it for it in items if it.properties["eo:cloud_cover"] <= SCENE_CLOUD_LIMIT]
    clear = sorted(clear, key=lambda it: it.properties["eo:cloud_cover"])[:MAX_CLEAR_SCENES]
    latest = items[-1]
    selected = {it.id: it for it in clear}
    selected[latest.id] = latest
    return sorted(selected.values(), key=lambda it: it.datetime)


def clip_asset(item, asset_key, out_path):
    href = item.assets[asset_key].href
    da = rioxarray.open_rasterio(href, masked=False)
    da = da.rio.clip_box(*aoi_bbox(), crs="EPSG:4326")
    da.rio.to_raster(out_path)
    return out_path


def fetch_dem(client):
    search = client.search(collections=["cop-dem-glo-30"], bbox=aoi_bbox(), limit=10)
    items = list(search.items())
    if not items:
        raise RuntimeError("No Copernicus DEM tile found for AOI")
    out = RASTER_DIR / "dem.tif"
    # AOI is small; a single 1x1 degree tile covers it
    da = rioxarray.open_rasterio(items[0].assets["data"].href, masked=True)
    da = da.rio.clip_box(*aoi_bbox(), crs="EPSG:4326")
    da.rio.to_raster(out)
    print(f"DEM: {items[0].id} -> {out.name} ({da.shape[-2]}x{da.shape[-1]} px)")


def main():
    client = Client.open(STAC_URL)
    items = search_scenes(client)
    print(f"{len(items)} usable scene-days in the last {DAYS_MONTH} days")
    selected = select_scenes(items)

    rows = []
    for it in selected:
        date = it.datetime.date().isoformat()
        cloud = it.properties["eo:cloud_cover"]
        print(f"Fetching {date} (cloud {cloud:.1f}%) ...")
        paths = {}
        for asset_key, label in BANDS.items():
            out = RASTER_DIR / f"{date}_{label}.tif"
            if not out.exists():
                clip_asset(it, asset_key, out)
            paths[label] = str(out)
        rows.append({
            "date": date,
            "item_id": it.id,
            "cloud_cover_pct": cloud,
            **{f"path_{k}": v for k, v in paths.items()},
        })

    pd.DataFrame(rows).to_csv(DATA_DIR / "scenes.csv", index=False)
    # Also record the full month's scene list for the report
    pd.DataFrame(
        [{"date": it.datetime.date().isoformat(),
          "cloud_cover_pct": it.properties["eo:cloud_cover"]} for it in items]
    ).to_csv(DATA_DIR / "all_scenes.csv", index=False)

    fetch_dem(client)
    print(f"Saved {len(rows)} scenes -> scenes.csv")


if __name__ == "__main__":
    main()
