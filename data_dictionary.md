# Data Dictionary — AquaBot Sensor Data

## Fields

| Column | Type | Unit | Expected Range | Description |
|--------|------|------|---------------|-------------|
| timestamp | ISO 8601 datetime | — | — | UTC timestamp of the reading |
| fish_id | string | — | — | Identifier of the AquaBot (always "fish-01" in this dataset) |
| lat | float | degrees | 32.65–32.72 | Latitude (WGS84) |
| lon | float | degrees | -117.20–-117.14 | Longitude (WGS84) |
| depth_m | float | meters | 0.0–15.0 | Measurement depth below surface |
| water_temp_c | float | °C | 12.0–25.0 | Water temperature |
| dissolved_oxygen_mgl | float | mg/L | 4.0–12.0 | Dissolved oxygen concentration |
| ph | float | — | 7.5–8.5 | pH level |
| turbidity_ntu | float | NTU | 0.0–50.0 | Water clarity (lower = clearer) |
| salinity_ppt | float | ppt | 30.0–36.0 | Salinity |
| battery_pct | float | % | 0–100 | Robot battery level at time of reading |

## Notes

- Readings are taken approximately every 10 minutes
- The AquaBot follows a survey pattern in San Diego Bay
- Environmental conditions vary with tides, weather, and depth
- This dataset contains deliberately injected anomalies for you to detect
