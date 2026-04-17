"""
pipeline.py — Data ingestion and anomaly detection for AquaBot sensor data.

Pure data module: no web framework imports. Loaded once at startup by main.py.
"""

from pathlib import Path
import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# Validation constants
# ---------------------------------------------------------------------------

PHYSICAL_BOUNDS: dict[str, tuple[float, float]] = {
    "water_temp_c":         (12.0, 25.0),
    "dissolved_oxygen_mgl": (4.0,  12.0),
    "ph":                   (7.5,   8.5),
    "turbidity_ntu":        (0.0,  50.0),
    "salinity_ppt":         (30.0, 36.0),
    "depth_m":              (0.0,  15.0),
    "battery_pct":          (0.0, 100.0),
    "lat":                  (32.65, 32.72),
    "lon":                  (-117.20, -117.14),
}

# Max allowed change between consecutive 10-minute readings
RATE_OF_CHANGE_LIMITS: dict[str, float] = {
    "water_temp_c":         5.0,
    "dissolved_oxygen_mgl": 3.0,
    "ph":                   0.5,
    "salinity_ppt":         3.0,
    "turbidity_ntu":        20.0,
}

# Sensor columns used for statistical analysis
SENSOR_COLS = [
    "water_temp_c", "dissolved_oxygen_mgl", "ph",
    "turbidity_ntu", "salinity_ppt", "depth_m", "battery_pct",
]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_data(path: str | Path) -> pd.DataFrame:
    """Load sensor CSV, add a 1-based row_index, and stringify timestamps."""
    df = pd.read_csv(path)
    df = df.reset_index(drop=True)
    df.insert(0, "row_index", df.index + 1)
    # Normalize timestamps: parse then re-serialize as a plain UTC ISO string.
    # pd.to_datetime handles the trailing Z in pandas 2.x.
    # The CSV has mixed formats: "...Z" and "...+00:00Z".
    # Strip a trailing Z after a timezone offset, then replace bare Z → +00:00.
    raw = df["timestamp"].str.replace(r"\+00:00Z$", "+00:00", regex=True)
    raw = raw.str.replace(r"Z$", "+00:00", regex=True)
    df["timestamp"] = (
        pd.to_datetime(raw, format="mixed", utc=True)
        .dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    return df


# ---------------------------------------------------------------------------
# Anomaly detectors
# ---------------------------------------------------------------------------

def detect_range_violations(df: pd.DataFrame) -> list[dict]:
    """
    Method 1 — Range validation.
    Flag any reading that is outside the physically expected bounds for each field.
    Zero false-positive rate for the defined bounds.
    """
    anomalies = []
    for col, (lo, hi) in PHYSICAL_BOUNDS.items():
        if col not in df.columns:
            continue
        mask = (df[col] < lo) | (df[col] > hi)
        for _, row in df[mask].iterrows():
            val = row[col]
            if val < lo:
                detail = f"Value {val} is below minimum {lo}"
            else:
                detail = f"Value {val} is above maximum {hi}"
            anomalies.append({
                "row_index": int(row["row_index"]),
                "timestamp": row["timestamp"],
                "field": col,
                "value": float(val),
                "method": "range_validation",
                "detail": detail,
            })
    return anomalies


def detect_iqr_outliers(df: pd.DataFrame, existing: list[dict]) -> list[dict]:
    """
    Method 2 — IQR statistical outlier detection.
    Uses Tukey's fence (Q1 - 1.5*IQR, Q3 + 1.5*IQR) on each sensor column.
    Only reports rows not already caught by range validation to avoid duplication.
    """
    already_flagged = {(a["row_index"], a["field"]) for a in existing}
    anomalies = []
    for col in SENSOR_COLS:
        if col not in df.columns:
            continue
        q1 = df[col].quantile(0.25)
        q3 = df[col].quantile(0.75)
        iqr = q3 - q1
        lo = q1 - 1.5 * iqr
        hi = q3 + 1.5 * iqr
        mask = (df[col] < lo) | (df[col] > hi)
        for _, row in df[mask].iterrows():
            key = (int(row["row_index"]), col)
            if key in already_flagged:
                continue
            val = row[col]
            anomalies.append({
                "row_index": int(row["row_index"]),
                "timestamp": row["timestamp"],
                "field": col,
                "value": float(val),
                "method": "iqr_statistical",
                "detail": f"Value {val:.4f} outside IQR fence [{lo:.4f}, {hi:.4f}]",
            })
    return anomalies


def detect_rate_of_change(df: pd.DataFrame) -> list[dict]:
    """
    Method 3 — Rate-of-change detection.
    Flags readings where the per-step delta exceeds expected limits for a 10-min interval.
    Catches transient spikes independently of static threshold checks.
    """
    anomalies = []
    # Work on a copy sorted by timestamp to ensure correct diff order
    sorted_df = df.sort_values("timestamp").reset_index(drop=True)
    for col, max_delta in RATE_OF_CHANGE_LIMITS.items():
        if col not in sorted_df.columns:
            continue
        deltas = sorted_df[col].diff().abs()
        mask = deltas > max_delta
        for idx in sorted_df[mask].index:
            row = sorted_df.loc[idx]
            delta_val = deltas.loc[idx]
            anomalies.append({
                "row_index": int(row["row_index"]),
                "timestamp": row["timestamp"],
                "field": col,
                "value": float(row[col]),
                "method": "rate_of_change",
                "detail": f"Step change of {delta_val:.4f} exceeds limit {max_delta} for {col}",
            })
    return anomalies


def detect_spatial_anomalies(df: pd.DataFrame) -> list[dict]:
    """
    Method 4 — Spatial validation.
    Flags GPS coordinates outside San Diego Bay bounding box.
    Catches GPS module failures (Null Island at 0,0) and out-of-area readings.
    """
    lat_lo, lat_hi = PHYSICAL_BOUNDS["lat"]
    lon_lo, lon_hi = PHYSICAL_BOUNDS["lon"]
    anomalies = []
    mask = (
        (df["lat"] < lat_lo) | (df["lat"] > lat_hi) |
        (df["lon"] < lon_lo) | (df["lon"] > lon_hi)
    )
    for _, row in df[mask].iterrows():
        anomalies.append({
            "row_index": int(row["row_index"]),
            "timestamp": row["timestamp"],
            "field": "lat/lon",
            "value": f"({row['lat']}, {row['lon']})",
            "method": "spatial_validation",
            "detail": (
                f"GPS position ({row['lat']}, {row['lon']}) is outside "
                f"San Diego Bay bbox lat[{lat_lo},{lat_hi}] lon[{lon_lo},{lon_hi}]"
            ),
        })
    return anomalies


def run_all_detectors(df: pd.DataFrame) -> list[dict]:
    """Run all four detectors and return a combined, sorted anomaly list."""
    range_anomalies = detect_range_violations(df)
    iqr_anomalies   = detect_iqr_outliers(df, range_anomalies)
    roc_anomalies   = detect_rate_of_change(df)
    spatial_anomalies = detect_spatial_anomalies(df)

    all_anomalies = range_anomalies + iqr_anomalies + roc_anomalies + spatial_anomalies
    all_anomalies.sort(key=lambda a: a["row_index"])
    return all_anomalies


# ---------------------------------------------------------------------------
# Module-level initialization — runs once on import
# ---------------------------------------------------------------------------

_DATA_PATH = Path(__file__).parent / "sensor_data.csv"

df: pd.DataFrame = load_data(_DATA_PATH)
anomalies: list[dict] = run_all_detectors(df)
anomaly_row_set: set[int] = {a["row_index"] for a in anomalies}
