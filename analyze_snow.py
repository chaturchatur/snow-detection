"""Compute snow metrics from the downloaded Sentinel-2 scenes.

Per scene: cloud-mask via SCL, NDSI = (green - swir) / (green + swir),
snow = NDSI > threshold. Crossed with the Copernicus DEM to estimate the
snowline (lowest elevation band where >=50% of valid pixels are snow).

Produces:
  output/data/snow_metrics.csv        - per-scene snow %, snowline, valid %
  output/data/snowline_profile_<date>.csv - snow fraction by elevation band
  output/rasters/<date>_NDSI.tif      - NDSI raster (for mapping)
"""
import numpy as np
import pandas as pd
import rioxarray
import xarray as xr

from config import NDSI_SNOW_THRESHOLD, DATA_DIR, RASTER_DIR, LAT, LON

# Sentinel-2 scene classification values to treat as invalid
SCL_INVALID = {0, 1, 3, 8, 9, 10}  # nodata, saturated, cloud shadow, cloud med/high, cirrus

ELEV_BIN_M = 100


def load_scene(date):
    green = rioxarray.open_rasterio(RASTER_DIR / f"{date}_B03.tif").squeeze().astype("float32")
    swir = rioxarray.open_rasterio(RASTER_DIR / f"{date}_B11.tif").squeeze().astype("float32")
    scl = rioxarray.open_rasterio(RASTER_DIR / f"{date}_SCL.tif").squeeze()
    # B11 and SCL are 20 m; resample to the 10 m green grid
    swir = swir.rio.reproject_match(green)
    scl = scl.rio.reproject_match(green)
    return green, swir, scl


def compute_ndsi(green, swir, scl):
    valid = ~np.isin(scl.values, list(SCL_INVALID)) & (green.values > 0) & (swir.values > 0)
    denom = green.values + swir.values
    with np.errstate(divide="ignore", invalid="ignore"):
        ndsi = (green.values - swir.values) / np.where(denom == 0, np.nan, denom)
    ndsi = np.where(valid, ndsi, np.nan)
    da = xr.DataArray(ndsi, coords=green.coords, dims=green.dims)
    da.rio.write_crs(green.rio.crs, inplace=True)
    return da, valid


def snowline_from_dem(snow_mask, valid, dem_on_grid, date):
    elev = dem_on_grid.values
    ok = valid & np.isfinite(elev)
    if ok.sum() == 0:
        return np.nan, pd.DataFrame()
    bins = np.arange(np.floor(elev[ok].min() / ELEV_BIN_M) * ELEV_BIN_M,
                     elev[ok].max() + ELEV_BIN_M, ELEV_BIN_M)
    rows = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        band = ok & (elev >= lo) & (elev < hi)
        n = band.sum()
        if n < 200:  # skip bands with too few pixels for a stable fraction
            continue
        frac = snow_mask[band].mean()
        rows.append({"elev_lo_m": lo, "elev_hi_m": hi, "n_pixels": int(n),
                     "snow_fraction": float(frac)})
    prof = pd.DataFrame(rows)
    snowline = np.nan
    if not prof.empty:
        above = prof[prof["snow_fraction"] >= 0.5]
        if not above.empty:
            snowline = float(above["elev_lo_m"].min())
    prof.to_csv(DATA_DIR / f"snowline_profile_{date}.csv", index=False)
    return snowline, prof


def site_pixel_snow(snow_mask_da):
    """Is the expedition point itself snow-covered in this scene?"""
    import pyproj
    tf = pyproj.Transformer.from_crs("EPSG:4326", snow_mask_da.rio.crs, always_xy=True)
    x, y = tf.transform(LON, LAT)
    val = snow_mask_da.sel(x=x, y=y, method="nearest").item()
    return bool(val) if np.isfinite(val) else None


def main():
    scenes = pd.read_csv(DATA_DIR / "scenes.csv")
    dem = rioxarray.open_rasterio(RASTER_DIR / "dem.tif", masked=True).squeeze()

    results = []
    for _, row in scenes.iterrows():
        date = row["date"]
        green, swir, scl = load_scene(date)
        ndsi, valid = compute_ndsi(green, swir, scl)
        ndsi.rio.to_raster(RASTER_DIR / f"{date}_NDSI.tif")

        snow = (ndsi.values > NDSI_SNOW_THRESHOLD) & valid
        valid_pct = 100 * valid.mean()
        snow_pct = 100 * snow[valid].mean() if valid.any() else np.nan

        dem_grid = dem.rio.reproject_match(green)
        snowline, _ = snowline_from_dem(snow, valid, dem_grid, date)

        snow_da = xr.DataArray(
            np.where(valid, snow.astype("float32"), np.nan),
            coords=green.coords, dims=green.dims)
        snow_da.rio.write_crs(green.rio.crs, inplace=True)
        at_site = site_pixel_snow(snow_da)

        results.append({
            "date": date,
            "cloud_cover_pct": row["cloud_cover_pct"],
            "valid_pixel_pct": round(valid_pct, 1),
            "snow_cover_pct": round(snow_pct, 1),
            "snowline_m": snowline,
            "snow_at_site": at_site,
        })
        print(f"{date}: snow {snow_pct:.1f}% of valid px "
              f"(valid {valid_pct:.0f}%), snowline ~{snowline} m, site snow: {at_site}")

    pd.DataFrame(results).to_csv(DATA_DIR / "snow_metrics.csv", index=False)


if __name__ == "__main__":
    main()
