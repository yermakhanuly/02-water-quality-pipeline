"""
main.py — FastAPI application for the AquaBot Water Quality Pipeline.

Endpoints:
  GET /               → redirect to frontend
  GET /data           → sensor readings (with optional time filter)
  GET /anomalies      → flagged anomaly records (with optional method/field filter)
  GET /summary        → per-sensor stats + anomaly breakdown
  GET /data/export    → download CSV (clean=true omits anomalous rows)
"""

import io
from collections import Counter
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import pipeline

app = FastAPI(title="AquaBot Water Quality API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _filter_by_time(
    df: pd.DataFrame,
    start: Optional[str],
    end: Optional[str],
) -> pd.DataFrame:
    """Return rows whose timestamp falls within [start, end] (inclusive)."""
    filtered = df.copy()
    # timestamps in the df are strings; parse on the fly for comparison
    ts = pd.to_datetime(filtered["timestamp"], utc=True)
    if start:
        try:
            start_ts = pd.to_datetime(start, utc=True)
        except Exception:
            raise HTTPException(status_code=400, detail=f"Invalid start timestamp: {start!r}")
        filtered = filtered[ts >= start_ts]
        ts = ts[filtered.index]
    if end:
        try:
            end_ts = pd.to_datetime(end, utc=True)
        except Exception:
            raise HTTPException(status_code=400, detail=f"Invalid end timestamp: {end!r}")
        filtered = filtered[ts <= end_ts]
    return filtered


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/static/index.html")


@app.get("/data")
def get_data(
    start: Optional[str] = Query(None, description="ISO 8601 start timestamp"),
    end:   Optional[str] = Query(None, description="ISO 8601 end timestamp"),
):
    """
    Return sensor readings, optionally filtered by time range.
    Each row includes an `is_anomaly` boolean flag.
    """
    filtered = _filter_by_time(pipeline.df, start, end)
    records = filtered.to_dict(orient="records")
    # Annotate each row with anomaly flag
    for rec in records:
        rec["is_anomaly"] = rec["row_index"] in pipeline.anomaly_row_set
    return {"count": len(records), "data": records}


@app.get("/anomalies")
def get_anomalies(
    method: Optional[str] = Query(None, description="Filter by detection method"),
    field:  Optional[str] = Query(None, description="Filter by sensor field"),
):
    """
    Return all flagged anomaly records.
    Optional filters: method (range_validation | iqr_statistical | rate_of_change | spatial_validation)
                      field (water_temp_c | ph | etc.)
    """
    results = pipeline.anomalies
    if method:
        results = [a for a in results if a["method"] == method]
    if field:
        results = [a for a in results if a["field"] == field]
    return {"total": len(results), "anomalies": results}


@app.get("/summary")
def get_summary():
    """
    Return per-sensor statistics (mean/min/max/std) and anomaly breakdown
    by method and by field.
    """
    df = pipeline.df

    # Per-sensor stats
    stat_cols = [
        "water_temp_c", "dissolved_oxygen_mgl", "ph",
        "turbidity_ntu", "salinity_ppt", "depth_m", "battery_pct",
    ]
    sensor_stats: dict[str, dict] = {}
    for col in stat_cols:
        if col in df.columns:
            sensor_stats[col] = {
                "mean": round(float(df[col].mean()), 4),
                "min":  round(float(df[col].min()),  4),
                "max":  round(float(df[col].max()),  4),
                "std":  round(float(df[col].std()),  4),
            }

    # Anomaly breakdown
    anomalous_rows = {a["row_index"] for a in pipeline.anomalies}
    by_method = dict(Counter(a["method"] for a in pipeline.anomalies))
    by_field  = dict(Counter(a["field"]  for a in pipeline.anomalies))

    return {
        "total_readings": len(df),
        "total_anomalies": len(anomalous_rows),
        "date_range": {
            "start": df["timestamp"].iloc[0],
            "end":   df["timestamp"].iloc[-1],
        },
        "anomaly_breakdown": {
            "by_method": by_method,
            "by_field":  by_field,
        },
        "sensor_stats": sensor_stats,
    }


@app.get("/data/export")
def export_data(
    clean: bool = Query(False, description="If true, exclude anomalous rows"),
):
    """
    Download sensor data as CSV.
    Pass ?clean=true to strip out anomalous rows.
    """
    df = pipeline.df.copy()
    if clean:
        df = df[~df["row_index"].isin(pipeline.anomaly_row_set)]
    # Remove the row_index helper column from the download
    df = df.drop(columns=["row_index"])

    buf = io.StringIO()
    df.to_csv(buf, index=False)
    buf.seek(0)

    filename = "sensor_data_clean.csv" if clean else "sensor_data.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
