# YOLO Detection Module Test Cases

| Test ID | Test Case | Input | Expected Output | Result |
| --- | --- | --- | --- | --- |
| TC-06 | Person Detection Accuracy | Camera frame with 5 people | Count = 5 (tolerance +/-1) | Pass |
| TC-07 | Empty Queue Detection | Camera frame with 0 people | Count = 0 | Pass |
| TC-08 | High Density Detection | Camera frame with 20+ people | Count within +/-2 of actual | Pass |
| TC-09 | Camera Disconnection | Camera feed lost mid-session | Error logged; system continues | Pass |
| TC-10 | Database Write | Detection event generated | Crowd count record inserted successfully | Pass |

## Execution Notes

- Endpoint for analysis: `POST /api/crowd/analyze`
- Endpoint for latest count: `GET /api/crowd/count`
- Upload field name: `file`
