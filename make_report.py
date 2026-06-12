"""Render plots, satellite maps, and REPORT.md from the fetched data."""
import datetime as dt

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rioxarray

from config import (
    LAT, LON, NDSI_SNOW_THRESHOLD, DATA_DIR, PLOTS_DIR, MAPS_DIR, RASTER_DIR, OUT,
    AOI_HALF_KM,
)


def plot_timeseries(hourly, daily, site_elev):
    fig, axes = plt.subplots(4, 1, figsize=(11, 13), sharex=False)

    ax = axes[0]
    ax.plot(daily["time"], daily["snow_depth_mean"] * 100, color="steelblue", lw=2)
    ax.set_ylabel("Snow depth (cm)")
    ax.set_title(f"Snow depth — daily mean, last 30 days (site {LAT:.4f}N {LON:.4f}E, ~{site_elev:.0f} m)")
    ax.grid(alpha=0.3)

    ax = axes[1]
    ax.bar(daily["time"], daily["snowfall_sum"], color="slateblue", label="Snowfall (cm)")
    rain = (daily["precipitation_sum"] - daily["snowfall_sum"] * 0.7).clip(lower=0)
    ax.bar(daily["time"], rain, bottom=daily["snowfall_sum"], color="seagreen",
           alpha=0.6, label="Other precip (mm w.e.)")
    ax.set_ylabel("Daily snowfall (cm) / precip")
    ax.set_title("Daily snowfall and precipitation")
    ax.legend(loc="upper right")
    ax.grid(alpha=0.3)

    ax = axes[2]
    ax.fill_between(daily["time"], daily["temperature_2m_min"], daily["temperature_2m_max"],
                    color="indianred", alpha=0.3, label="Daily min–max")
    ax.plot(daily["time"], daily["temperature_2m_max"], color="firebrick", lw=1)
    ax.plot(daily["time"], daily["temperature_2m_min"], color="navy", lw=1)
    ax.axhline(0, color="k", ls="--", lw=1, label="0°C")
    ax.set_ylabel("Temperature 2 m (°C)")
    ax.set_title("Daily temperature range")
    ax.legend(loc="upper left")
    ax.grid(alpha=0.3)

    ax = axes[3]
    ax.plot(daily["time"], daily["wind_speed_10m_max"], color="darkorange", lw=2, label="Max wind")
    ax.plot(daily["time"], daily["wind_gusts_10m_max"], color="firebrick", lw=1.5,
            ls="--", label="Max gusts")
    ax.set_ylabel("Wind (km/h)")
    ax.set_title("Daily max wind speed and gusts")
    ax.legend(loc="upper left")
    ax.grid(alpha=0.3)

    for ax in axes:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "month_overview.png", dpi=140)
    plt.close(fig)

    # Recent week, hourly detail
    fig, axes = plt.subplots(3, 1, figsize=(11, 10), sharex=True)
    ax = axes[0]
    ax.plot(hourly["time"], hourly["snow_depth"] * 100, color="steelblue", lw=1.5)
    ax.set_ylabel("Snow depth (cm)")
    ax.set_title("Last 7 days + 3-day forecast — hourly (forecast right of dashed line)")
    ax.grid(alpha=0.3)

    ax = axes[1]
    ax.plot(hourly["time"], hourly["temperature_2m"], color="firebrick", lw=1.5)
    ax.axhline(0, color="k", ls="--", lw=1)
    ax.set_ylabel("Temp 2 m (°C)")
    ax.grid(alpha=0.3)

    ax = axes[2]
    ax.plot(hourly["time"], hourly["freezing_level_height"], color="purple", lw=1.5)
    ax.axhline(site_elev, color="k", ls=":", lw=1.5, label=f"Site elevation ({site_elev:.0f} m)")
    ax.set_ylabel("Freezing level (m)")
    ax.legend(loc="upper left")
    ax.grid(alpha=0.3)

    now = pd.Timestamp(dt.datetime.now())
    for ax in axes:
        ax.axvline(now, color="gray", ls="--", lw=1)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "week_detail.png", dpi=140)
    plt.close(fig)


def render_scene_maps(metrics):
    for _, row in metrics.iterrows():
        date = row["date"]
        rgb = rioxarray.open_rasterio(RASTER_DIR / f"{date}_RGB.tif")
        ndsi = rioxarray.open_rasterio(RASTER_DIR / f"{date}_NDSI.tif").squeeze()

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 6.5))
        ax1.imshow(np.transpose(rgb.values[:3], (1, 2, 0)))
        ax1.set_title(f"Sentinel-2 true color — {date} (cloud {row['cloud_cover_pct']:.0f}%)")
        ax1.axis("off")

        im = ax2.imshow(ndsi.values, cmap="RdBu", vmin=-1, vmax=1)
        snow_pct = row["snow_cover_pct"]
        ax2.set_title(f"NDSI (blue = snow) — {snow_pct:.0f}% snow-covered")
        ax2.axis("off")
        fig.colorbar(im, ax=ax2, fraction=0.04, label="NDSI")

        # Mark the expedition point (center of AOI)
        for ax, shape in ((ax1, rgb.shape[1:]), (ax2, ndsi.shape)):
            ax.plot(shape[1] / 2, shape[0] / 2, marker="*", color="yellow",
                    markersize=16, markeredgecolor="black")

        fig.suptitle(f"{2*AOI_HALF_KM:.0f} km × {2*AOI_HALF_KM:.0f} km around {LAT:.4f}N {LON:.4f}E")
        fig.tight_layout()
        fig.savefig(MAPS_DIR / f"scene_{date}.png", dpi=140)
        plt.close(fig)


def plot_satellite_trend(metrics):
    m = metrics.copy()
    m["date"] = pd.to_datetime(m["date"])
    solid = m[m["valid_pixel_pct"] >= 50]
    hazy = m[(m["valid_pixel_pct"] < 50) & m["snow_cover_pct"].notna()]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 8), sharex=True)
    ax1.plot(solid["date"], solid["snow_cover_pct"], "o-", color="steelblue",
             label="≥50% of AOI visible")
    ax1.plot(hazy["date"], hazy["snow_cover_pct"], "o", mfc="none", color="steelblue",
             label="<50% visible (less reliable)")
    ax1.set_ylabel("Snow-covered % of AOI")
    ax1.set_title("Sentinel-2 snow cover trend (hollow points = mostly cloud-blocked passes)")
    ax1.set_ylim(0, 100)
    ax1.legend()
    ax1.grid(alpha=0.3)

    ax2.plot(solid["date"], solid["snowline_m"], "o-", color="firebrick")
    ax2.plot(hazy["date"], hazy["snowline_m"], "o", mfc="none", color="firebrick")
    site_elev = pd.read_csv(DATA_DIR / "site_meta.csv")["model_elevation_m"].iloc[0]
    ax2.axhline(site_elev, color="k", ls=":", label=f"Site elevation ({site_elev:.0f} m)")
    ax2.set_ylabel("Snowline elevation (m)")
    ax2.set_title("Snowline trend")
    ax2.legend()
    ax2.grid(alpha=0.3)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "satellite_trend.png", dpi=140)
    plt.close(fig)


def plot_snowline(metrics):
    profs = []
    metrics = metrics[metrics["valid_pixel_pct"] >= 50]
    for _, row in metrics.iterrows():
        p = DATA_DIR / f"snowline_profile_{row['date']}.csv"
        if p.exists():
            df = pd.read_csv(p)
            df["date"] = row["date"]
            profs.append(df)
    if not profs:
        return
    fig, ax = plt.subplots(figsize=(8, 6))
    for df in profs:
        mid = (df["elev_lo_m"] + df["elev_hi_m"]) / 2
        ax.plot(df["snow_fraction"] * 100, mid, marker="o", ms=3, label=df["date"].iloc[0])
    ax.axvline(50, color="k", ls="--", lw=1, label="50% (snowline)")
    ax.set_xlabel("Snow-covered fraction (%)")
    ax.set_ylabel("Elevation (m)")
    ax.set_title("Snow fraction vs elevation (Sentinel-2 NDSI × Copernicus DEM)")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "snowline_profile.png", dpi=140)
    plt.close(fig)


def write_report(hourly, daily, metrics, all_scenes, site_elev):
    now = dt.datetime.now()
    past_hourly = hourly[hourly["time"] <= pd.Timestamp(now)]
    latest = past_hourly.dropna(subset=["snow_depth"]).iloc[-1]

    snow_24h = past_hourly[past_hourly["time"] >= pd.Timestamp(now - dt.timedelta(hours=24))]["snowfall"].sum()
    snow_72h = past_hourly[past_hourly["time"] >= pd.Timestamp(now - dt.timedelta(hours=72))]["snowfall"].sum()
    month_snowfall = daily["snowfall_sum"].sum()
    depth_30d_ago = daily["snow_depth_mean"].dropna().iloc[0]
    depth_now = latest["snow_depth"]
    fl_recent = past_hourly.tail(72)["freezing_level_height"]

    tmin = daily["temperature_2m_min"].min()
    tmax = daily["temperature_2m_max"].max()
    gust_max = daily["wind_gusts_10m_max"].max()

    lines = [
        f"# Expedition Snow & Weather Report — {LAT:.5f}N, {LON:.5f}E",
        "",
        f"*Generated {now:%Y-%m-%d %H:%M} IST. Site model elevation ≈ {site_elev:.0f} m "
        f"(Pir Panjal / Bara Bhangal region, Himachal Pradesh).*",
        "",
        "## Current snow state",
        "",
        f"- **Snow depth now: {depth_now*100:.0f} cm** "
        f"(30 days ago: {depth_30d_ago*100:.0f} cm → net change {100*(depth_now-depth_30d_ago):+.0f} cm)",
        f"- **Fresh snowfall: {snow_24h:.1f} cm in last 24 h, {snow_72h:.1f} cm in last 72 h**",
        f"- Total snowfall over the past month: {month_snowfall:.0f} cm",
        f"- Freezing level (last 3 days): {fl_recent.min():.0f}–{fl_recent.max():.0f} m "
        f"(site is at ~{site_elev:.0f} m)",
        "",
        "## Satellite observations (Sentinel-2, 10 m)",
        "",
        "| Date | Cloud % | Valid px % | Snow cover % | Snowline (m) | Snow at site |",
        "|---|---|---|---|---|---|",
    ]
    def fmt(v, spec=".0f"):
        return f"{v:{spec}}" if pd.notna(v) else "—"

    for _, r in metrics.iterrows():
        site = {True: "yes", False: "no"}.get(r["snow_at_site"], "cloud")
        lines.append(
            f"| {r['date']} | {fmt(r['cloud_cover_pct'])} | {fmt(r['valid_pixel_pct'])} "
            f"| {fmt(r['snow_cover_pct'])} | {fmt(r['snowline_m'])} | {site} |")

    lines += [
        "",
        f"*Snow cover % is over a {2*AOI_HALF_KM:.0f}×{2*AOI_HALF_KM:.0f} km box centered on the site, "
        f"NDSI > {NDSI_SNOW_THRESHOLD}, cloud-masked. Snowline = lowest 100 m elevation band "
        "with ≥50% snow.*",
        "",
        "![Satellite trend](plots/satellite_trend.png)",
        "",
        "### Imagery (newest first — yellow star marks the site)",
        "",
        "*Scenes where at least half the area was cloud-blocked are listed in the table "
        "above but not shown here; their PNGs are in `output/maps/`.*",
        "",
    ]
    usable = metrics[metrics["valid_pixel_pct"] >= 50]
    for _, r in usable.sort_values("date", ascending=False).iterrows():
        lines += [
            f"**{r['date']}** — {r['snow_cover_pct']:.0f}% snow-covered, "
            f"cloud {r['cloud_cover_pct']:.0f}%",
            "",
            f"![Sentinel-2 {r['date']}](maps/scene_{r['date']}.png)",
            "",
        ]
    lines += [
        "## Month context",
        "",
        f"- Temperature range over the month: {tmin:.1f}°C to {tmax:.1f}°C",
        f"- Strongest gusts: {gust_max:.0f} km/h",
        f"- {len(all_scenes)} satellite passes in the month; "
        f"{(all_scenes['cloud_cover_pct'] < 30).sum()} with <30% cloud",
        "",
        "![Month overview](plots/month_overview.png)",
        "",
        "![Last week hourly detail](plots/week_detail.png)",
        "",
        "![Snowline profile](plots/snowline_profile.png)",
        "",
        "## Notes for the expedition",
        "",
    ]

    notes = []
    if snow_72h >= 20:
        notes.append(f"**Significant fresh snow ({snow_72h:.0f} cm in 72 h) — elevated avalanche "
                     "risk; allow 24–48 h settling time and avoid loaded slopes.**")
    elif snow_72h >= 5:
        notes.append(f"Moderate fresh snow ({snow_72h:.0f} cm in 72 h) — watch for wind slabs "
                     "on lee slopes.")
    else:
        notes.append(f"Little fresh snow in the last 72 h ({snow_72h:.1f} cm) — surface is likely "
                     "consolidated spring snowpack.")

    if fl_recent.mean() >= site_elev:
        notes.append("Freezing level is at/above the site: daytime melt and wet, heavy snow; "
                     "overnight refreeze likely gives firm crust — start early, expect postholing "
                     "by midday, and consider crampons for morning travel.")
    else:
        notes.append("Freezing level is below the site: snowpack staying frozen — colder travel "
                     "but firmer surfaces.")

    if depth_now - depth_30d_ago < -0.1:
        notes.append(f"Snowpack is in melt-out ({100*(depth_30d_ago-depth_now):.0f} cm lost over "
                     "the month) — expect weakening snow bridges over streams/crevasses.")

    snls = metrics["snowline_m"].dropna()
    if not snls.empty:
        notes.append(f"Observed snowline is around **{snls.iloc[-1]:.0f} m** in the latest clear "
                     f"scene — below that expect mostly bare ground, above it continuous snow.")

    notes.append("Model data is from Open-Meteo (~9 km grid, downscaled); treat absolute snow "
                 "depth as indicative. Satellite snow extent is directly observed and more "
                 "trustworthy for where snow is.")

    lines += [f"- {n}" for n in notes]
    lines += [
        "",
        "## Files",
        "",
        "- `output/plots/month_overview.png` — snow depth, snowfall, temperature, wind (30 days)",
        "- `output/plots/week_detail.png` — hourly last 7 days + 3-day forecast",
        "- `output/plots/snowline_profile.png` — snow fraction vs elevation",
        "- `output/maps/scene_<date>.png` — true color + NDSI snow maps",
        "- `output/data/*.csv` — raw metrics",
        "",
    ]
    (OUT / "REPORT.md").write_text("\n".join(lines))
    print(f"Wrote {OUT / 'REPORT.md'}")


def main():
    hourly = pd.read_csv(DATA_DIR / "hourly_recent.csv", parse_dates=["time"])
    daily = pd.read_csv(DATA_DIR / "daily_month.csv", parse_dates=["time"])
    metrics = pd.read_csv(DATA_DIR / "snow_metrics.csv")
    all_scenes = pd.read_csv(DATA_DIR / "all_scenes.csv")
    site_elev = pd.read_csv(DATA_DIR / "site_meta.csv")["model_elevation_m"].iloc[0]

    plot_timeseries(hourly, daily, site_elev)
    render_scene_maps(metrics)
    plot_satellite_trend(metrics)
    plot_snowline(metrics)
    write_report(hourly, daily, metrics, all_scenes, site_elev)


if __name__ == "__main__":
    main()
