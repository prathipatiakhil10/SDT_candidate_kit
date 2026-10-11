\# DECISIONS.md



1\. \*\*Indexes.\*\* The unique `emp\_code` index prevents duplicate employees. The unique `(emp\_code, date)` attendance index prevents duplicate daily attendance and resolves simultaneous punch-in requests. Other indexes support department, date, status, and late-minute queries. I use a stable employee-code sort to make leaderboard ordering predictable.



2\. \*\*Punch-in race.\*\* If two identical requests arrive together, MongoDB's unique attendance index allows only one insert. The other insert raises `DuplicateKeyError`, which the API converts to HTTP 409 Conflict.



3\. \*\*Ties.\*\* Employees with equal total late minutes receive the same rank. The leaderboard can return more than `limit` employees when a tie reaches the cutoff. This avoids arbitrarily excluding an employee with an equal result.



4\. \*\*Headcount.\*\* The department summary starts its roster aggregation from employees joined by the end of the selected month. It counts that roster separately from attendance statistics, so employees with no logs still contribute to headcount.



5\. \*\*Scaling.\*\* For 100 times more data, I would review query plans and index usage, then optimize the most expensive aggregation queries using realistic, larger datasets.
