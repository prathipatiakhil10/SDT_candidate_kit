# DECISIONS.md

1. **Indexes.** The unique `emp_code` index prevents duplicate employees. The unique `(emp_code, date)` attendance index prevents duplicate daily records and protects against simultaneous punch-ins. Other indexes support date, status, department, and late-minute queries. Stable sorting makes leaderboard results predictable.

2. **Punch-in race.** If two identical requests arrive together, MongoDB's unique attendance index allows only one insert. The other raises `DuplicateKeyError`, which the API should convert to HTTP 409 Conflict.

3. **Ties.** Employees with equal total late minutes receive the same rank. Applying the limit after ranking may return more employees than the requested limit when a tie reaches the cutoff. This avoids unfairly excluding employees with equal results.

4. **Headcount.** The department summary counts employees who joined by the end of the selected month. It calculates roster headcount separately from attendance statistics, so employees without attendance logs are still counted.

5. **Scaling.** With 100 times more data, I would inspect slow queries using `explain("executionStats")`, verify index usage, and benchmark aggregations with realistic larger datasets. I would optimize expensive pipeline stages and avoid unnecessary collection scans while preserving the required results.