# AquaBot Water Quality Pipeline

A data processing pipeline and visualization tool for 30-day AquaBot sensor data from San Diego Bay. Ingests raw CSV sensor readings, detects anomalies using four independent methods, exposes a REST API, and serves an interactive web dashboard.

---

## Setup

### Requirements

- Python 3.10+

### Install and run

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

Open your browser at **http://localhost:8000**.

The API docs (Swagger UI) are available at **http://localhost:8000/docs**.

---

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /data` | All sensor readings. Optional `?start=` and `?end=` ISO 8601 filters. Each row includes `is_anomaly`. |
| `GET /anomalies` | All flagged anomalies. Optional `?method=` and `?field=` filters. |
| `GET /summary` | Per-sensor stats (mean/min/max/std) and anomaly breakdown by method and field. |
| `GET /data/export` | Download CSV. Add `?clean=true` to exclude anomalous rows. |

---

## Anomaly Detection Methods

Four independent detectors run on startup. Their results are combined and deduplicated by row.

### 1. Range Validation (`range_validation`)

Flags readings that are physically impossible — outside the documented bounds for each sensor (e.g., negative turbidity, dissolved oxygen above 12 mg/L, pH above 8.5 in seawater). This is the authoritative first pass: zero false-positive rate for correctly defined bounds.

**Why:** Physical impossibility is the strongest signal. If a sensor reports a value that can't exist in the real world, that row is unambiguously bad regardless of what the rest of the data looks like.

### 2. IQR Statistical Outliers (`iqr_statistical`)

Computes Tukey's fence `[Q1 − 1.5×IQR, Q3 + 1.5×IQR]` for each sensor column across the full dataset. Flags rows that fall outside this fence and weren't already caught by range validation.

**Why:** Provides a data-driven second opinion. Useful for catching values that are technically within the physical envelope but are statistically extreme for this particular deployment (e.g., a temperature reading that is valid in theory but 6 standard deviations from the deployment mean).

### 3. Rate-of-Change Detection (`rate_of_change`)

Checks the absolute delta between consecutive 10-minute readings. Flags steps that exceed per-sensor limits (e.g., temperature changing by more than 5°C in 10 minutes).

**Why:** A sudden spike that returns to normal in the next reading is a classic sensor glitch pattern. This method catches it independently of whether the spike value is technically within range — and it also provides corroborating evidence for the same anomalies caught by range validation.

### 4. Spatial Validation (`spatial_validation`)

Flags GPS coordinates outside the San Diego Bay bounding box (lat 32.65–32.72, lon −117.20–−117.14). Specifically catches the GPS null-island failure mode (lat=0, lon=0) and any position that the robot physically couldn't have reached.

**Why:** GPS module failures have a distinct signature (returning 0,0 or a fixed erroneous position) that is invisible to sensor-value checks. This is a separate failure mode that deserves its own detector.

---

## Anomalies Found

The dataset contains the following injected anomalies (detected automatically):

| Approx. Row | Field | Issue | Method(s) |
|---|---|---|---|
| ~801  | dissolved_oxygen_mgl | Impossibly low value (~0.5 mg/L) | range, iqr, roc |
| ~1801 | ph | Value far outside seawater range (~12.0) | range, iqr |
| ~2001 | depth_m | Negative depth | range, iqr |
| ~2801 | water_temp_c | Spike to impossible temperature (~45°C) | range, iqr, roc |
| ~3201 | turbidity_ntu | Physically impossible negative reading | range, iqr |
| ~3501–3520 | salinity_ppt | 20 consecutive readings oscillating 15/50 ppt | range, iqr |
| ~3801 | multiple sensors | All-zeros row (sensor reset event) | range, iqr, roc |
| ~4001 | battery_pct | Battery > 100% | range, iqr |
| ~4401 | lat/lon | GPS module returned 0,0 (Null Island) | range, spatial |
| ~4601 | dissolved_oxygen_mgl | Spike to impossibly high value (~25 mg/L) | range, iqr, roc |
| ~4706–4710 | water_temp_c | Rapid temperature ramp | range, iqr, roc |

---

## Architecture

```
sensor_data.csv
      │
      ▼
pipeline.py          Pure data module
  load_data()         → parse CSV, add row_index
  detect_range_violations()
  detect_iqr_outliers()
  detect_rate_of_change()
  detect_spatial_anomalies()
  run_all_detectors() → combined anomaly list
      │
      ▼
main.py              FastAPI HTTP layer
  GET /data           → filtered rows + is_anomaly flag
  GET /anomalies      → anomaly records
  GET /summary        → stats + breakdown
  GET /data/export    → CSV download
      │
      ▼
static/index.html    Single-file frontend (Plotly.js CDN)
  Time-series chart   (temperature + dissolved oxygen, dual y-axis)
  GPS path map        (Plotly scattermapbox, open-street-map tiles)
  Summary table       (per-sensor mean/min/max/std)
  Anomaly breakdown   (by method and by field)
  Anomaly list        (paginated table)
```

**Why `pipeline.py` is separate from `main.py`:** The data logic has no dependency on the web framework. Keeping it separate makes the detectors testable in isolation (`python pipeline.py`) and makes it straightforward to swap FastAPI for another framework or to run the pipeline as a CLI script.

**Why in-memory instead of a database:** The dataset is ~5,000 rows (~430 KB). Loading it into a pandas DataFrame on startup takes under 100 ms and uses less than 10 MB of RAM. A database would add operational complexity with no performance benefit at this scale.

---

## Discussion Notes

**Edge vs. cloud processing:** Running anomaly detection on the robot (Raspberry Pi) enables real-time alerting and reduces bandwidth — critical if the robot is offshore. But edge hardware has limited compute, no easy model updates, and failures are hard to debug remotely. A hybrid approach works best: run simple range-validation checks on the edge to filter obvious sensor failures, and send all data to the cloud for the heavier statistical analysis.

**Scaling to high-frequency data:** At 1 reading/second over years, the dataset grows to billions of rows. Solutions: time-series database (TimescaleDB, InfluxDB) for efficient range queries; stream processing (Kafka + Flink) for real-time anomaly detection; pre-aggregated summaries for the dashboard; columnar storage (Parquet) for batch analysis.

**Sensor calibration drift:** Slow drift is hard to detect because the values remain technically valid for weeks. Approaches: compare against reference sensors or known calibration standards; fit a rolling baseline model and flag readings that deviate from the expected trend; periodic recalibration logs that the pipeline can cross-reference.

**Production alerting:** A real system would watch a message queue fed by the pipeline, apply severity tiers (INFO / WARNING / CRITICAL), deduplicate alerts for sustained anomalies (don't page 1,000 times for a 20-row salinity fault), and route alerts to PagerDuty / Slack / email based on the anomaly type and time of day.

---

## What I'd Improve With More Time

- **Anomaly severity scoring** — assign a confidence and severity level to each detection so scientists can triage
- **Configurable thresholds** — expose the bounds and IQR multiplier as query parameters so users can tune sensitivity in the UI
- **Persistent storage** — write processed results to a SQLite or TimescaleDB database so the pipeline doesn't re-run from scratch on every restart
- **Unit tests** — pytest suite for each detector with known-anomaly fixtures derived from `validation_hints.json`
- **Streaming ingest** — replace CSV polling with a WebSocket or MQTT subscriber for live robot data
- **Anomaly confidence intervals** — show uncertainty bands around the rolling baseline on the chart
