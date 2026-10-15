# REVIEW.md

## Verified Defects

### 1. Regularizing Attendance to LEAVE or ABSENT

**Where:** `regularize_attendance()`

**Problem:** Changing an existing punched attendance record to `LEAVE` or `ABSENT` can fail because the old punch timestamps remain in the record.

**How to reproduce:** Start with a `PRESENT` record containing punch timestamps and regularize it to `LEAVE` without supplying new timestamps. The starter can return HTTP 422.

**Fix:** Clear the old punch timestamps when changing the status to `LEAVE` or `ABSENT`, and include the changes in the audit history.

**Status:** Fixed.

### 2. Attendance List Explain Query

**Where:** `explain_endpoint()` ? `attendance_list`

**Problem:** The explain query ignores the requested status filter and uses a hardcoded limit of 20 instead of the requested pagination.

**How to reproduce:** Call `/admin/explain/attendance_list` with a status filter and non-default pagination, then compare the explained query with the requested parameters.

**Fix:** Include the status filter and requested pagination parameters in the explained query.

**Status:** Fixed.

### 3. Employee Monthly Explain Pipeline

**Where:** `explain_endpoint()` ? `employee_monthly`

**Problem:** The explained aggregation counts records instead of explaining the actual monthly analytics pipeline.

**How to reproduce:** Compare `/admin/explain/employee_monthly` with `/analytics/employees/{emp_code}/monthly`.

**Fix:** Update the explain branch to use the monthly aggregation stages and metrics.

**Status:** Fixed.

### 4. Department Summary Explain Pipeline

**Where:** `explain_endpoint()` ? `department_summary`

**Problem:** The explained aggregation omits the employee lookup, roster headcount, and department statistics used by the real summary endpoint.

**How to reproduce:** Compare the explained pipeline with `/analytics/departments/summary`.

**Fix:** Explain both the attendance statistics aggregation and the employee roster headcount aggregation.

**Status:** Fixed.

### 5. Late Leaderboard Explain Pipeline

**Where:** `explain_endpoint()` ? `late_leaderboard`

**Problem:** The explained aggregation omits the employee lookup, optional department filtering, ranking, and rank-based cutoff logic.

**How to reproduce:** Compare the explained pipeline with `/analytics/leaderboard/late`, including a request with a department filter.

**Fix:** Include the employee lookup, optional department filter, ranking, and tie-aware limit logic.

**Status:** Fixed.

### 6. Department Trend Explain Pipeline

- **Location:** `explain_endpoint()`, `department_trend` branch.
- **Problem:** The starter explain aggregation omits the daily aggregation, date densification, headcount, attendance rate, and seven-day moving average.
- **How to reproduce:** Compare `/admin/explain/department_trend` with `/analytics/departments/{department}/trend`.
- **Fix:** Include the relevant department filtering and trend pipeline stages in the explain operation.
- **Status:** Fixed.


### 7. Department Trend With No Attendance Logs

- **Location:** Original starter `department_trend()`.
- **Problem:** Starting the aggregation from attendance records means `$densify` cannot generate rows if the pipeline has no input documents.
- **Symptom:** A department with employees but no attendance records in the requested period may return no daily rows.
- **Fix:** Generate the daily date series independently of attendance records and fill missing attendance counts with zero.
**Verification:** Tested the current endpoint for `Engineering` from `2020-01-01` to `2020-01-07`. It returned all seven daily rows with zero attendance counts. This confirms the current implementation handles an empty attendance period; the original starter behavior still needs separate verification before counting this as a confirmed starter defect.

### 8. Concurrent Duplicate Employee Creation

- **Location:** Original starter `create_employee()`.
- **Problem:** Concurrent requests can both pass the initial existence check. The unique index rejects one insert, but the duplicate-key error may not be handled.
- **Symptom:** A concurrent duplicate creation request may return HTTP 500 instead of HTTP 409.
- **Fix:** Catch `DuplicateKeyError` and return HTTP 409 Conflict.
- **Verification:** Eight simultaneous create requests for EMP987655 produced one HTTP 201 Created and seven HTTP 409 Conflict responses, with no unexpected errors.

### 9. Overnight-Shift Attendance Corrections

**Where:** Original starter `regularize_attendance()`.

**Problem:** The correction logic requires each supplied punch timestamp to fall on the same IST calendar date as the attendance record. For an overnight shift, a valid punch-out after midnight can belong to the previous shift date and be rejected.

**How to reproduce:** Create an overnight-shift attendance record and attempt to correct its punch-out to a valid time after midnight on the following calendar day.

**Fix:** Validate timestamps against the employee's shift date, accounting for overnight shifts, rather than requiring both timestamps to have the same calendar date.

**Verification:** Tested the corrected API with EMP987654 on a 22:00�06:00 shift. A 22:30 IST punch-in on 2026-10-14 and a 06:15 IST punch-out on 2026-10-15 were accepted. The attendance date remained 2026-10-14 and work_hours was 7.75. The original defect was identified by inspecting the starter code.
### 10. Punch-In Duplicate-Key Exception Import

- **Location:** Original starter imports and `punch_in()`.
- **Problem:** The starter's duplicate-key handler references `DuplicateKeyError` without importing it.
- **Symptom:** A duplicate punch-in may trigger `NameError` instead of the intended conflict response.
- **Fix:** Import `DuplicateKeyError` from `pymongo.errors` and handle the exception explicitly.
-**Verification:** Inspected the original starter and confirmed `DuplicateKeyError` was used without being imported. Tested the fixed API with a duplicate punch-in; it returned HTTP 409 and the attendance record count remained 5 before and after.
### 11. Analytics Include Attendance Before the Joining Date

**Where:** Original starter `employee_monthly()` and `department_summary()`.

**Problem:** The attendance aggregations filter records by reporting month but do not consistently exclude records dated before the employee's `joined_on` date. The monthly endpoint calculates working days from the joining date while its attendance aggregation can include earlier records.

**How to reproduce:** In a disposable test database, create an employee who joins partway through a month and an attendance record for that employee dated before their joining date but within the same month. Request the employee's monthly analytics and the department summary.

**Fix:** Exclude attendance records dated before the relevant employee's joining date in both analytics aggregations.

**Verification:** Reproduced with test employee EMP987656 (joined 2026-10-15): the original API accepted a PRESENT punch-in dated 2026-10-14, and monthly analytics counted 1.0 present days (8.33%). After the fix, the same punch-in returns HTTP 422 and monthly analytics reports 0.0 present days (0.0%). Department-summary impact remains to be verified.

- The unique `(emp_code, date)` attendance index prevents duplicate daily attendance records, including simultaneous punch-ins. Duplicate-key errors are converted to HTTP 409.
- `punch_out()` uses a conditional update so simultaneous attempts cannot both successfully close the same record.
- `regularize_attendance()` already uses a compare-and-set filter for concurrent corrections in the starter. This is not considered a starter defect.
- Monthly analytics counts presence on weekdays and applies half-day weighting.
- The department trend uses `$densify` to fill missing dates and `$setWindowFields` to calculate the seven-day moving average.
- The late leaderboard uses `$rank`, so tied employees can share a rank and the result may contain more rows than the requested limit.
- The department summary separates employee roster headcount from attendance statistics, allowing employees with no logs to contribute to headcount.

## Verification Notes

- The explain endpoint branches listed above were updated to match their corresponding analytics queries or pipelines.
- Query plans were checked against the current development database. The tested queries and lookups used indexes.
- The current development dataset is small. These checks do not establish performance at approximately 100,000 attendance records.
- Additional starter defects must be inspected and verified before being added to this review.
