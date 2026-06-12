"""Fetch weather/snow model data from Open-Meteo for the expedition site.

Produces:
  output/data/hourly_recent.csv  - hourly metrics for the last DAYS_RECENT days
  output/data/daily_month.csv    - daily aggregates for the last DAYS_MONTH days
  output/data/site_meta.csv      - model elevation and request metadata
"""
import datetime as dt

import pandas as pd
import requests

from config import LAT, LON, DAYS_RECENT, DAYS_MONTH, DATA_DIR

HOURLY_VARS = [
    "snow_depth",
    "snowfall",
    "temperature_2m",
    "freezing_level_height",
    "wind_speed_10m",
    "wind_gusts_10m",
    "precipitation",
]

DAILY_VARS = [
    "snowfall_sum",
    "precipitation_sum",
    "temperature_2m_max",
    "temperature_2m_min",
    "wind_speed_10m_max",
    "wind_gusts_10m_max",
]


def fetch_recent_hourly():
    r = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": LAT,
            "longitude": LON,
            "hourly": ",".join(HOURLY_VARS),
            "past_days": DAYS_RECENT,
            "forecast_days": 3,
            "timezone": "Asia/Kolkata",
        },
        timeout=60,
    )
    r.raise_for_status()
    payload = r.json()
    df = pd.DataFrame(payload["hourly"])
    df["time"] = pd.to_datetime(df["time"])
    return df, payload["elevation"]


def fetch_month_daily():
    end = dt.date.today()
    start = end - dt.timedelta(days=DAYS_MONTH)
    # The archive lags a few days behind realtime; the forecast API's past_days
    # covers the gap, so query the archive and let merge_daily() fill the tail.
    r = requests.get(
        "https://archive-api.open-meteo.com/v1/archive",
        params={
            "latitude": LAT,
            "longitude": LON,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "daily": ",".join(DAILY_VARS),
            "hourly": "snow_depth",
            "timezone": "Asia/Kolkata",
        },
        timeout=60,
    )
    r.raise_for_status()
    payload = r.json()
    daily = pd.DataFrame(payload["daily"])
    daily["time"] = pd.to_datetime(daily["time"])

    snow = pd.DataFrame(payload["hourly"])
    snow["time"] = pd.to_datetime(snow["time"])
    snow_daily = (
        snow.set_index("time")["snow_depth"].resample("D").mean().rename("snow_depth_mean")
    )
    daily = daily.merge(snow_daily, left_on="time", right_index=True, how="left")
    return daily


def fetch_recent_daily_from_forecast():
    """Daily aggregates from the forecast API to fill the archive's realtime lag."""
    r = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": LAT,
            "longitude": LON,
            "daily": ",".join(DAILY_VARS),
            "hourly": "snow_depth",
            "past_days": 14,
            "forecast_days": 1,
            "timezone": "Asia/Kolkata",
        },
        timeout=60,
    )
    r.raise_for_status()
    payload = r.json()
    daily = pd.DataFrame(payload["daily"])
    daily["time"] = pd.to_datetime(daily["time"])
    snow = pd.DataFrame(payload["hourly"])
    snow["time"] = pd.to_datetime(snow["time"])
    snow_daily = (
        snow.set_index("time")["snow_depth"].resample("D").mean().rename("snow_depth_mean")
    )
    daily = daily.merge(snow_daily, left_on="time", right_index=True, how="left")
    return daily


def merge_daily(archive: pd.DataFrame, recent: pd.DataFrame) -> pd.DataFrame:
    merged = pd.concat([archive, recent]).drop_duplicates(subset="time", keep="last")
    merged = merged.sort_values("time").reset_index(drop=True)
    # Drop trailing rows where the archive has no data yet and recent didn't cover
    merged = merged[merged["time"] <= pd.Timestamp(dt.date.today())]
    return merged


def main():
    hourly, elevation = fetch_recent_hourly()
    hourly.to_csv(DATA_DIR / "hourly_recent.csv", index=False)

    archive = fetch_month_daily()
    recent = fetch_recent_daily_from_forecast()
    daily = merge_daily(archive, recent)
    daily.to_csv(DATA_DIR / "daily_month.csv", index=False)

    pd.DataFrame(
        [{"lat": LAT, "lon": LON, "model_elevation_m": elevation,
          "fetched_at": dt.datetime.now().isoformat(timespec="seconds")}]
    ).to_csv(DATA_DIR / "site_meta.csv", index=False)

    print(f"Model elevation: {elevation} m")
    print(f"Hourly rows: {len(hourly)}  ({hourly['time'].min()} → {hourly['time'].max()})")
    print(f"Daily rows:  {len(daily)}  ({daily['time'].min().date()} → {daily['time'].max().date()})")
    last = hourly.dropna(subset=["snow_depth"]).iloc[-1]
    print(f"Latest snow depth: {last['snow_depth']} m at {last['time']}")


if __name__ == "__main__":
    main()
