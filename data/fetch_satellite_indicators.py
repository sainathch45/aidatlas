"""Computes REAL rainfall and vegetation anomalies for the India
districts directly from Earth Engine satellite data -- not cited from
a news article, computed live from CHIRPS precipitation and MODIS NDVI.

Confirmed before writing this (not assumed): CHIRPS daily data lags
~40 days (latest available 2026-08-31 as of this run), MODIS NDVI lags
~26 days (latest 2026-09-14). Windows below are chosen to fall fully
inside confirmed-available data, not "today."

    python fetch_satellite_indicators.py
"""

import json

import ee

ee.Initialize(project="ai-builder-cup-aidatlas")

CHIRPS = ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY").select("precipitation")
MODIS_NDVI = ee.ImageCollection("MODIS/061/MOD13Q1").select("NDVI")
HIST_YEARS = list(range(2016, 2026))  # 10-year baseline, 2016-2025


def period_sum(collection, start, end):
    return collection.filterDate(start, end).sum()


def rainfall_anomaly(lat, lon, current_start, current_end, hist_month_day):
    """current_start/end: 'YYYY-MM-DD'. hist_month_day: (start 'MM-DD', end 'MM-DD')
    for the same calendar window in each of HIST_YEARS.
    """
    point = ee.Geometry.Point([lon, lat])
    current_img = period_sum(CHIRPS, current_start, current_end).rename("current")

    hist_images = [
        period_sum(CHIRPS, f"{y}-{hist_month_day[0]}", f"{y}-{hist_month_day[1]}")
        for y in HIST_YEARS
    ]
    hist_mean_img = ee.ImageCollection(hist_images).mean().rename("historical_mean")

    combined = ee.Image.cat([current_img, hist_mean_img])
    result = combined.reduceRegion(ee.Reducer.mean(), point, scale=5566, maxPixels=1e9).getInfo()
    current_val = result.get("current")
    hist_val = result.get("historical_mean")
    if current_val is None or hist_val in (None, 0):
        return None
    pct_of_normal = round(100 * current_val / hist_val, 1)
    return {
        "current_mm": round(current_val, 1),
        "historical_mean_mm": round(hist_val, 1),
        "pct_of_normal": pct_of_normal,
        "deficit_pct": round(100 - pct_of_normal, 1),
    }


def ndvi_anomaly(lat, lon, current_start, current_end, hist_month_day):
    point = ee.Geometry.Point([lon, lat])
    current_img = (
        MODIS_NDVI.filterDate(current_start, current_end).mean().multiply(0.0001).rename("current")
    )
    hist_images = [
        MODIS_NDVI.filterDate(f"{y}-{hist_month_day[0]}", f"{y}-{hist_month_day[1]}").mean().multiply(0.0001)
        for y in HIST_YEARS
    ]
    hist_mean_img = ee.ImageCollection(hist_images).mean().rename("historical_mean")
    combined = ee.Image.cat([current_img, hist_mean_img])
    result = combined.reduceRegion(ee.Reducer.mean(), point, scale=250, maxPixels=1e9).getInfo()
    current_val = result.get("current")
    hist_val = result.get("historical_mean")
    if current_val is None or hist_val is None:
        return None
    return {
        "current_ndvi": round(current_val, 3),
        "historical_mean_ndvi": round(hist_val, 3),
        "anomaly": round(current_val - hist_val, 3),
    }


# Maharashtra: real 2026 monsoon season (Jun-Aug, fully inside confirmed
# CHIRPS availability) vs the same calendar window averaged 2016-2025.
MAHARASHTRA_DISTRICTS = [
    ("Solapur", 17.6599, 75.9064),
    ("Beed", 18.9894, 75.7601),
    ("Hingoli", 19.7172, 77.1492),
    ("Jalna", 19.8347, 75.8816),
    ("Dharashiv", 18.1860, 76.0419),
    ("Latur", 18.4088, 76.5604),
]

# Assam: the real flood-triggering window (cloudburst 19 Jul 2026 plus
# the lead-up) vs the same calendar window averaged 2016-2025 -- shows
# how extreme the actual rainfall was, satellite-confirmed.
ASSAM_DISTRICTS = [
    ("Golaghat", 26.5106, 93.9647),
    ("Sivasagar", 26.9850, 94.6378),
]

output = {"MHD": {}, "ASF": {}}

print("=== Maharashtra: 2026 monsoon (Jun-Aug) vs 2016-2025 mean ===")
for name, lat, lon in MAHARASHTRA_DISTRICTS:
    rain = rainfall_anomaly(lat, lon, "2026-06-01", "2026-08-31", ("06-01", "08-31"))
    # MOD13Q1 is a 16-day composite, not daily -- confirmed real granule
    # dates near this window are 2026-08-13, 08-29, 09-14 before writing
    # this, so the query window has to be wide enough to actually contain
    # one, not just span the calendar days we care about.
    ndvi = ndvi_anomaly(lat, lon, "2026-09-05", "2026-09-20", ("09-05", "09-20"))
    print(name, "rain:", rain, "ndvi:", ndvi)
    output["MHD"][name] = {"rainfall": rain, "ndvi": ndvi}

print("\n=== Assam: Jul 10-25 2026 flood window vs 2016-2025 mean ===")
for name, lat, lon in ASSAM_DISTRICTS:
    rain = rainfall_anomaly(lat, lon, "2026-07-10", "2026-07-25", ("07-10", "07-25"))
    print(name, "rain:", rain)
    output["ASF"][name] = {"rainfall": rain}

with open("satellite_indicators.json", "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2)
print("\nSaved satellite_indicators.json")
