# Forecasting Module Test Cases

| Test ID | Test Case | Input | Expected Output | Result |
| --- | --- | --- | --- | --- |
| TC-11 | Forecast Generation | 7 days of queue history | 48 forecast records for next 4 hours | Pass |
| TC-12 | Peak Hour Detection | Historical data with Monday peaks | Forecast indicates Monday peak hours | Pass |
| TC-13 | Insufficient Data Handling | Less than 24 hours of history | Graceful warning logged; no crash | Pass |
| TC-14 | Forecast API Retrieval | `GET /queue/forecast` | JSON array of predicted counts with timestamps | Pass |
