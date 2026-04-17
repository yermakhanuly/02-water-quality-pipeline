# Task 2: Marine Water Quality Data Pipeline & Visualization

## Context

Our AquaBots collect water quality measurements as they swim survey patterns. After a mission, scientists need to analyze this data — but raw sensor data is messy. Sensors drift, glitch, and sometimes produce impossible readings. GPS modules occasionally report positions on land. Before anyone can draw conclusions from the data, it needs to be cleaned, validated, and visualized.

Your job is to build a data processing pipeline and visualization tool for a 30-day dataset from a simulated AquaBot deployment.

## What We Provide

- `sensor_data.csv` — 30 days of simulated water quality data (~5,000 rows) from a deployment in San Diego Bay. Contains realistic data with **deliberately injected anomalies** for you to detect.
- `data_dictionary.md` — Description of each field and its expected ranges

The dataset contains approximately 15–20 anomalies of various types. Some are obvious, some are subtle. Part of the challenge is deciding what counts as anomalous.

## What You Build

### Core Requirements

1. **Data Ingestion** — Load the CSV and parse it into a usable format
2. **Anomaly Detection** — Implement at least **two different methods** for flagging suspicious readings. Examples:
   - Statistical thresholds (z-score, IQR-based)
   - Moving average / rolling window deviation
   - Range validation (physically impossible values)
   - Spatial validation (GPS on land)
   - Rate-of-change checks (sensor readings that jump too fast)
3. **REST API** — Expose at least these endpoints:
   - `GET /data` — query sensor data with optional time range filter (`?start=...&end=...`)
   - `GET /anomalies` — list all flagged anomalies with the detection method that caught them
   - `GET /summary` — basic statistics (mean, min, max, std for each sensor, total anomaly count)
4. **Visualization Frontend** — A web page that displays:
   - A **time-series chart** of at least 2 sensor readings (e.g., temperature and dissolved oxygen) across the full dataset
   - **Anomalies visually highlighted** on the chart (different color, marker, or annotation)
   - A **date range selector** to zoom into specific periods
   - A **summary panel** showing key statistics

### Stretch Goals

- Multiple anomaly detection methods with configurable sensitivity (let the user adjust thresholds)
- GPS visualization — plot the AquaBot's path on a map, highlight anomalous positions
- Export cleaned (anomaly-free) data as CSV download
- Comparison view of raw vs. cleaned data
- Anomaly classification breakdown (what type of anomaly, which sensor)

## Technology

Use whatever you're most productive in. Some good options:
- Python: FastAPI/Flask + pandas for processing + Plotly/Matplotlib for charts
- Node.js: Express + any charting library
- Frontend: React, Vue, vanilla JS — whatever you prefer
- Plotly.js, Chart.js, D3, or any charting library

## Deliverables

- Source code in a git repo with meaningful commits
- A README covering: setup instructions, what anomaly detection methods you chose and why, architecture decisions, what you'd improve with more time
- Be prepared to demo and walk through your pipeline logic

## Discussion Topics (for the in-person walkthrough)

- Should anomaly detection run on the robot (edge processing on a Raspberry Pi) or in the cloud? What are the tradeoffs?
- How would you scale this pipeline to handle years of high-frequency data (readings every second instead of every 10 minutes)?
- How would you handle sensor calibration drift — where readings are technically "valid" but slowly becoming less accurate over weeks?
- What would a production alerting system look like — how do you notify a scientist when something interesting (or broken) is detected in real-time?
