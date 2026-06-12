"""Shared configuration for the expedition snow analysis pipeline."""
from pathlib import Path

# Expedition site
LAT = 33.04917
LON = 76.83113

# Area of interest: half-width of the box around the site, in km
AOI_HALF_KM = 5.0

# Analysis windows
DAYS_RECENT = 7    # hourly weather detail
DAYS_MONTH = 30    # daily aggregates + satellite search

# NDSI snow threshold (standard value from the literature)
NDSI_SNOW_THRESHOLD = 0.4

# Sentinel-2 scene selection — analyze every pass; per-pixel cloud masking
# handles overcast scenes (they just contribute fewer valid pixels)
MAX_CLEAR_SCENES = 50
SCENE_CLOUD_LIMIT = 100.0

STAC_URL = "https://earth-search.aws.element84.com/v1"

BASE = Path(__file__).parent
OUT = BASE / "output"
DATA_DIR = OUT / "data"
PLOTS_DIR = OUT / "plots"
MAPS_DIR = OUT / "maps"
RASTER_DIR = OUT / "rasters"

for d in (DATA_DIR, PLOTS_DIR, MAPS_DIR, RASTER_DIR):
    d.mkdir(parents=True, exist_ok=True)


def aoi_bbox():
    """Lon/lat bounding box of the AOI (west, south, east, north)."""
    import math
    dlat = AOI_HALF_KM / 111.32
    dlon = AOI_HALF_KM / (111.32 * math.cos(math.radians(LAT)))
    return (LON - dlon, LAT - dlat, LON + dlon, LAT + dlat)
