\# REVIEW.md



| # | Where (function / line) | What is wrong | How you'd notice it (test, input, or symptom) | How you fixed it |

|---|---|---|---|---|

| 1 | `create\_employee()` | The endpoint returned the raw MongoDB document, so `created\_at` could be serialized as a datetime string instead of the contract's epoch milliseconds. | Create an employee and inspect the `created\_at` value in the response. | Return `serialize(doc)` after inserting the document, which converts the datetime to epoch milliseconds. |



\## Checked, not considered a defect



\- The unique `(emp\_code, date)` attendance index prevents duplicate daily attendance records, including simultaneous punch-in requests. Duplicate-key errors are handled as HTTP 409.

\- The department summary counts headcount from the employee roster separately from attendance statistics, so employees with zero logs are included.

\- The late leaderboard uses rank-based cutoff logic, so tied employees can share a rank and the result can contain more rows than `limit`.
