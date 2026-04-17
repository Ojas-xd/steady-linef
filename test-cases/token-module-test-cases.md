# Token Generation Module Test Cases

| Test ID | Test Case | Input | Expected Output | Result |
| --- | --- | --- | --- | --- |
| TC-01 | QR Token Generation | Customer scans QR | Unique token ID generated | Pass |
| TC-02 | Concurrent Token Generation | 5 simultaneous QR scans | 5 unique sequential token IDs | Pass |
| TC-03 | Token Status Update | Staff marks token as Served | Token status changes to Completed | Pass |
| TC-04 | Invalid Token Lookup | `GET /token/INVALID99` | 404 Not Found response returned | Pass |
| TC-05 | Queue Position Accuracy | 3 active tokens in queue | Position 4 returned for new token | Pass |
