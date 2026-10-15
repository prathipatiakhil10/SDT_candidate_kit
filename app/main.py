"""
Employee Attendance & Analytics API - STARTER

Run:  uvicorn app.main:app --port 8000
Env:  MONGO_URI, MONGO_DB (a local .env is loaded for convenience)

This file was written quickly by a colleague who has left the company. The happy path
works, but nobody has reviewed it. Read PROBLEM_STATEMENT.docx for what is expected of you,
openapi.yaml for the contract and DATA_MODEL.md for what is stored in MongoDB.
"""
import os
import re
from datetime import date as Date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, ConfigDict, field_validator
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import PyMongoError, DuplicateKeyError
from pymongo.errors import DuplicateKeyError
load_dotenv()

client = MongoClient(
    os.getenv("MONGO_URI", "mongodb://localhost:27017"),
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=5000,
)
db = client[os.getenv("MONGO_DB", "attendance_db")]

IST = timezone(timedelta(hours=5, minutes=30))
MIN_EPOCH_MS = 946684800000   # 2000-01-01 UTC
MAX_EPOCH_MS = 4102444800000  # 2100-01-01 UTC

PRESENCE = {"PRESENT", "WFH", "ON_DUTY"}
ALL_STATUSES = PRESENCE | {"ABSENT", "LEAVE"}
app = FastAPI(title="Employee Attendance & Analytics API", version="2.0.0")


@app.on_event("startup")
def create_indexes():
    """Create required indexes without conflicting with existing default names."""
    db.employees.create_index(
        [("emp_code", ASCENDING)], unique=True
    )
    db.employees.create_index(
        [("department", ASCENDING), ("emp_code", ASCENDING)]
    )

    db.employees.create_index(
        [("joined_on", ASCENDING)]
    )

    db.attendance_logs.create_index(
        [("emp_code", ASCENDING), ("date", ASCENDING)],
        unique=True,
    )
    db.attendance_logs.create_index(
        [("date", DESCENDING), ("emp_code", ASCENDING)]
    )
    db.attendance_logs.create_index(
        [("status", ASCENDING), ("date", DESCENDING)]
    )
    db.attendance_logs.create_index(
        [("date", ASCENDING), ("late_minutes", DESCENDING), ("emp_code", ASCENDING)]
    )



# ------------------------------- Models -------------------------------------

class EmployeeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    emp_code: str = Field(pattern=r"^EMP\d{4,6}$")
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=254)
    department: str = Field(min_length=1, max_length=50)
    shift_start: str = "09:30"
    shift_end: str = "18:30"
    joined_on: str

    @field_validator("email")
    @classmethod
    def valid_email(cls, v):
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v):
            raise ValueError("email must be a valid email address")
        return v

    @field_validator("shift_start", "shift_end")
    @classmethod
    def valid_shift_time(cls, v):
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", v):
            raise ValueError("time must use HH:MM format")
        return v

    @field_validator("joined_on")
    @classmethod
    def valid_joined_date(cls, v):
        parse_date(v, "joined_on")
        return v

    @field_validator("shift_end")
    @classmethod
    def different_shift_end(cls, v, info):
        start = info.data.get("shift_start")
        if start is not None and v == start:
            raise ValueError("shift_start and shift_end must differ")
        return v
class PunchInIn(BaseModel):
    emp_code: str
    punched_at: Optional[int] = None
    status: str = "PRESENT"


class PunchOutIn(BaseModel):
    emp_code: str
    punched_at: Optional[int] = None

class AttendanceCorrection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Optional[str] = None
    punch_in: Optional[int] = None
    punch_out: Optional[int] = None
    reason: str = Field(min_length=5, max_length=200)
    regularized_by: str = Field(min_length=1, max_length=50)

    @field_validator("punch_in", "punch_out")
    @classmethod
    def valid_timestamps(cls, v, info):
        if v is not None:
            validate_epoch_ms(v, info.field_name)
        return v


# ------------------------------- Helpers ------------------------------------

def parse_date(value: str, field: str = "date") -> Date:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise HTTPException(422, f"{field} must be in YYYY-MM-DD format")
    try:
        return Date.fromisoformat(value)
    except ValueError:
        raise HTTPException(422, f"{field} must be a valid calendar date")


def parse_month(value: str) -> tuple[Date, Date]:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}", value):
        raise HTTPException(422, "month must use YYYY-MM format")
    try:
        first = Date.fromisoformat(value + "-01")
    except ValueError:
        raise HTTPException(422, "month must be a valid calendar month")
    if first.month == 12:
        next_month = Date(first.year + 1, 1, 1)
    else:
        next_month = Date(first.year, first.month + 1, 1)
    return first, next_month - timedelta(days=1)


def validate_epoch_ms(value, field="timestamp") -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise HTTPException(422, f"{field} must be an integer timestamp in milliseconds")
    if value < MIN_EPOCH_MS or value > MAX_EPOCH_MS:
        raise HTTPException(422, f"{field} is outside the allowed millisecond timestamp range")
    return value


def ms_to_utc_naive(value: int) -> datetime:
    validate_epoch_ms(value)
    try:
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc).replace(microsecond=0, tzinfo=None)
    except (ValueError, OverflowError, OSError):
        raise HTTPException(422, "Invalid timestamp")


def utc_naive_to_ms(value: Optional[datetime]):
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp() * 1000)


def serialize(value):
    """Convert Mongo dates to epoch milliseconds recursively for API responses."""
    if isinstance(value, dict):
        return {k: serialize(v) for k, v in value.items() if k != "_id"}
    if isinstance(value, list):
        return [serialize(v) for v in value]
    if isinstance(value, datetime):
        return utc_naive_to_ms(value)
    return value
    start, _ = shift_bounds(emp, attendance_date)
    elapsed_seconds = (local - start).total_seconds()
    # Apply the grace period to the exact elapsed duration, then floor the
    # reported lateness to whole minutes (e.g. 09:40:01 for 09:30 => 10).
    if elapsed_seconds <= 10 * 60:
        return 0
    return max(0, int(elapsed_seconds // 60))


def calc_work_hours(punch_in: Optional[datetime], punch_out: Optional[datetime]) -> Optional[float]:
    if punch_in is None or punch_out is None:
        return None
    seconds = (stored_utc(punch_out) - stored_utc(punch_in)).total_seconds()
    value = (Decimal(str(seconds)) / Decimal("3600")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(value)
def shift_bounds(emp, attendance_date):
    shift_start = datetime.strptime(
        f"{attendance_date} {emp['shift_start']}",
        "%Y-%m-%d %H:%M"
    ).replace(tzinfo=IST)

    shift_end_date = attendance_date

    # Overnight shift: end time falls on the next calendar day.
    if emp["shift_end"] <= emp["shift_start"]:
        shift_end_date = (
            datetime.strptime(attendance_date, "%Y-%m-%d")
            + timedelta(days=1)
        ).date().isoformat()

    shift_end = datetime.strptime(
        f"{shift_end_date} {emp['shift_end']}",
        "%Y-%m-%d %H:%M"
    ).replace(tzinfo=IST)

    return shift_start, shift_end

def calc_overtime(punch_out: Optional[datetime], emp: dict, attendance_date: str) -> int:
    if punch_out is None:
        return 0
    _, end = shift_bounds(emp, attendance_date)
    minutes = int((stored_utc(punch_out).astimezone(IST) - end).total_seconds() // 60)
    return minutes if minutes >= 30 else 0


def get_employee(emp_code: str):
    emp = db.employees.find_one({"emp_code": emp_code})
    if not emp:
        raise HTTPException(404, "Employee not found")
    return emp

def get_attendance(emp_code: str, attendance_date: str):
    rec = db.attendance_logs.find_one({"emp_code": emp_code, "date": attendance_date})
    if not rec:
        raise HTTPException(404, "Attendance record not found")
    return rec


def half_up(value, places=2):
    if value is None:
        return None
    quantum = Decimal("1").scaleb(-places)
    return float(Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP))


def weekday_count(start: Date, end: Date) -> int:
    if end < start:
        return 0
    days = (end - start).days + 1
    weeks, rem = divmod(days, 7)
    total = weeks * 5
    for i in range(rem):
        if (start + timedelta(days=weeks * 7 + i)).weekday() < 5:
            total += 1
    return total


def validate_date_range(date_from: Optional[str], date_to: Optional[str]):
    start = parse_date(date_from, "date_from") if date_from else None
    end = parse_date(date_to, "date_to") if date_to else None
    if start and end and start > end:
        raise HTTPException(422, "date_from must be on or before date_to")
    return start, end


# -------------------------------- Health ------------------------------------

@app.get("/health")
def health():
    try:
        db.command("ping")
        return {"status": "ok"}
    except PyMongoError:
        raise HTTPException(503, "MongoDB is unavailable")

    q = {"department": department} if department is not None else {}
    total = db.employees.count_documents(q)
    items = list(db.employees.find(q, {"_id": 0}).sort("emp_code", ASCENDING).skip((page - 1) * page_size).limit(page_size))
    return {"items": serialize(items), "total": total, "page": page, "page_size": page_size}


# ------------------------------- Attendance ---------------------------------


@app.post("/employees", status_code=201)
def create_employee(body: EmployeeIn):
    doc = body.model_dump()
    doc["created_at"] = datetime.now(timezone.utc).replace(
        microsecond=0, tzinfo=None
    )

    try:
        db.employees.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, "emp_code already exists")

    return serialize(doc)


@app.get("/employees")
def list_employees(
    emp_code: Optional[str] = None,
    department: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    if page < 1:
        raise HTTPException(status_code=422, detail="Page must be at least 1")

    if page_size < 1 or page_size > 100:
        raise HTTPException(
            status_code=422,
            detail="Page size must be between 1 and 100",
        )

    q = {}
    if emp_code:
        q["emp_code"] = emp_code
    if department:
        q["department"] = department

    skip = (page - 1) * page_size
    total = db.employees.count_documents(q)

    items = [
        serialize(doc)
        for doc in db.employees.find(q, {"_id": 0})
        .sort("emp_code", 1)
        .skip(skip)
        .limit(page_size)
    ]

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }

@app.post("/attendance/punch-in", status_code=201)
def punch_in(body: PunchInIn):
    emp = get_employee(body.emp_code)
    status = body.status.upper()
    if status not in PRESENCE:
        raise HTTPException(422, "Punch-in status must be PRESENT, WFH, or ON_DUTY")
    punch = ms_to_utc_naive(body.punched_at) if body.punched_at is not None else datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None)
    local = punch.replace(tzinfo=timezone.utc).astimezone(IST)
    attendance_date = local.date().isoformat()
    # Overnight shifts: early-morning punch-ins before shift end belong to prior shift day.
    if emp["shift_end"] <= emp["shift_start"] and local.strftime("%H:%M") < emp["shift_end"]:
        attendance_date = (local.date() - timedelta(days=1)).isoformat()
    if attendance_date < emp["joined_on"]:
        raise HTTPException(422, "Attendance date cannot be before employee joined_on")
    late = calc_late_minutes(punch, emp, attendance_date)
    doc = {
        "emp_code": body.emp_code, "date": attendance_date, "status": status,
        "punch_in": punch, "punch_out": None, "work_hours": None,
        "late_minutes": late, "overtime_minutes": 0, "half_day": False, "history": [],
        "created_at": datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None),
    }
    try:
        db.attendance_logs.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, "Already punched in for this date")
    return serialize(doc)


@app.post("/attendance/punch-out")
def punch_out(body: PunchOutIn):
    emp = get_employee(body.emp_code)
    out = ms_to_utc_naive(body.punched_at) if body.punched_at is not None else datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None)
    out_aware = out.replace(tzinfo=timezone.utc)
    # Select the most recent punch-in at or before this punch-out, including
    # closed records. This prevents an old open record from being closed when
    # the latest matching shift has already been punched out.
    record = db.attendance_logs.find_one(
        {"emp_code": body.emp_code, "punch_in": {"$ne": None, "$lte": out}},
        sort=[("punch_in", DESCENDING)],
    )
    if record is None:
        raise HTTPException(404, "Punch-in record not found")
    if record.get("punch_out") is not None:
        raise HTTPException(409, "Already punched out")
    punch_in = stored_utc(record["punch_in"])
    if out_aware <= punch_in:
        raise HTTPException(422, "Punch-out must be after punch-in")
    if out_aware - punch_in > timedelta(hours=24):
        raise HTTPException(422, "Punch-out must be within 24 hours of punch-in")
    work_hours = calc_work_hours(punch_in, out_aware)
    late = calc_late_minutes(punch_in, emp, record["date"])
    overtime = calc_overtime(out, emp, record["date"])
    update = db.attendance_logs.update_one(
        {"_id": record["_id"], "punch_out": None},
        {"$set": {"punch_out": out, "work_hours": work_hours, "overtime_minutes": overtime, "half_day": work_hours < 4.5}},
    )
    if update.modified_count != 1:
        raise HTTPException(409, "Attendance was already updated")
    return serialize(db.attendance_logs.find_one({"_id": record["_id"]}, {"_id": 0}))


@app.get("/attendance")
def list_attendance(
    emp_code: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    start, end = validate_date_range(date_from, date_to)
    q = {}
    if emp_code is not None:
        q["emp_code"] = emp_code
    if start or end:
        q["date"] = {}
        if start:
            q["date"]["$gte"] = start.isoformat()
        if end:
            q["date"]["$lte"] = end.isoformat()
    if status is not None:
        if status not in ALL_STATUSES:
            raise HTTPException(422, "Invalid attendance status")
        q["status"] = status
    total = db.attendance_logs.count_documents(q)
    docs = list(db.attendance_logs.find(q, {"_id": 0}).sort([("date", DESCENDING), ("emp_code", ASCENDING)]).skip((page - 1) * page_size).limit(page_size))
    return {"items": serialize(docs), "total": total, "page": page, "page_size": page_size}


# ------------------------------- Query plans --------------------------------

@app.patch("/attendance/{emp_code}/{date}")
def regularize_attendance(
    emp_code: str,
    date: str,
    body: AttendanceCorrection,
):
    from datetime import date as date_type

    try:
        parsed_date = date_type.fromisoformat(date)
        if parsed_date.isoformat() != date:
            raise ValueError
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail="date must be in YYYY-MM-DD format",
        )

    if body.status is None and body.punch_in is None and body.punch_out is None:
        raise HTTPException(
            status_code=422,
            detail="Provide at least one field to correct",
        )

    emp = db.employees.find_one({"emp_code": emp_code})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    record = db.attendance_logs.find_one({"emp_code": emp_code, "date": date})
    if not record:
        raise HTTPException(status_code=404, detail="Attendance record not found")

    changes = {}
    before_after = {}
    new_status = body.status.upper() if body.status else record.get("status")

    if body.status is not None:
        if new_status not in ALL_STATUSES:
            raise HTTPException(status_code=422, detail="Invalid attendance status")
        if new_status != record.get("status"):
            changes["status"] = new_status
            before_after["status"] = {
              "from": record.get("status"),
              "to": new_status,
            }
    new_punch_in = record.get("punch_in")
    new_punch_out = record.get("punch_out")

    for field, value in (("punch_in", body.punch_in), ("punch_out", body.punch_out)):
        if value is None:
            continue

        try:
            converted = datetime.fromtimestamp(value / 1000, tz=timezone.utc).replace(microsecond=0)
        except (ValueError, OverflowError, OSError):
            raise HTTPException(status_code=422, detail=f"Invalid {field} timestamp")

        local_value = converted.astimezone(IST)
        expected_date = local_value.date()

        overnight_shift = emp["shift_end"] <= emp["shift_start"]
        if overnight_shift:
            if field == "punch_in" and local_value.strftime("%H:%M") < emp["shift_end"]:
                expected_date -= timedelta(days=1)
            elif field == "punch_out" and expected_date == parsed_date + timedelta(days=1):
                expected_date -= timedelta(days=1)

        if expected_date.isoformat() != date:
            raise HTTPException(
                status_code=422,
                detail=f"{field} must belong to the attendance date in IST",
            )

        stored = converted.replace(tzinfo=None)
        if stored != record.get(field):
            changes[field] = stored
            before_after[field] = {
                "from": record[field].isoformat() if record.get(field) else None,
                "to": stored.isoformat(),
            }
            if field == "punch_in":
                new_punch_in = stored
            else:
                new_punch_out = stored

    if new_status in {"ABSENT", "LEAVE"}:
        for field, old_value in (
            ("punch_in", new_punch_in),
            ("punch_out", new_punch_out),
        ):
            if old_value is not None:
                changes[field] = None
                before_after[field] = {
                    "from": old_value.isoformat(),
                    "to": None,
                }
        new_punch_in = None
        new_punch_out = None
    if new_status in {"ABSENT", "LEAVE"} and (new_punch_in is not None or new_punch_out is not None):
        raise HTTPException(
            status_code=422,
            detail="ABSENT and LEAVE must not have punch timestamps",
        )

    if new_status in PRESENCE and new_punch_in is None:
        raise HTTPException(status_code=422, detail="Present attendance requires punch-in")

    if new_punch_in is not None and new_punch_out is not None and new_punch_out < new_punch_in:
        raise HTTPException(status_code=422, detail="Punch-out must be after punch-in")

    if "punch_in" in changes or "status" in changes:
        changes["late_minutes"] = (
            calc_late_minutes(new_punch_in, emp, date)
            if new_punch_in is not None and new_status in PRESENCE
            else 0
        )

    if "punch_in" in changes or "punch_out" in changes or "status" in changes:
        if new_punch_in is not None and new_punch_out is not None:
            work_hours = float(half_up((new_punch_out - new_punch_in).total_seconds() / 3600, 2))
            local_out = new_punch_out.replace(tzinfo=timezone.utc).astimezone(IST)
            eh, em = map(int, emp["shift_end"].split(":"))
            shift_end = datetime.fromisoformat(date).replace(hour=eh, minute=em, tzinfo=IST)
            if emp["shift_end"] <= emp["shift_start"]:
                shift_end += timedelta(days=1)
            overtime = max(0, int((local_out - shift_end).total_seconds() // 60))
            if overtime < 30:
                overtime = 0
            changes.update({
                "work_hours": work_hours,
                "overtime_minutes": overtime,
                "half_day": work_hours < 4.5,
            })
        else:
            changes.update({
                "work_hours": None,
                "overtime_minutes": 0,
                "half_day": False,
            })


    if not before_after:
        raise HTTPException(
            status_code=422,
            detail="No fields changed",
        )

    if before_after:
        history_entry = {
            "at": datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None),
            "by": body.regularized_by,
            "reason": body.reason.strip(),
            "changes": before_after,
        }
        db.attendance_logs.update_one(
            {"_id": record["_id"]},
            {"$set": changes, "$push": {"history": history_entry}},
        )

    return serialize(
    db.attendance_logs.find_one(
        {"_id": record["_id"]},
        {"_id": 0}
    )
)
# ------------------------------- Analytics ----------------------------------
@app.get("/analytics/employees/{emp_code}/monthly")
def employee_monthly(emp_code: str, month: str):
    emp = get_employee(emp_code)
    first, last = parse_month(month)
    first_day = max(first, parse_date(emp["joined_on"], "joined_on"))
    working_days = weekday_count(first_day, last)

    records = list(db.attendance_logs.aggregate([
        {
            "$match": {
                "emp_code": emp_code,
                "date": {
                    "$gte": first_day.isoformat(),
                    "$lte": last.isoformat()
                }
            }
        },
        {
            "$group": {
                "_id": None,
                "present_days": {
                    "$sum": {
                        "$cond": [
                            {
                                "$and": [
                                    {"$in": ["$status", list(PRESENCE)]},
                                    {
                                        "$in": [
                                            {
                                                "$dayOfWeek": {
                                                    "$dateFromString": {
                                                        "dateString": "$date"
                                                    }
                                                }
                                            },
                                            [2, 3, 4, 5, 6]
                                        ]
                                    }
                                ]
                            },
                            {"$cond": ["$half_day", 0.5, 1]},
                            0
                        ]
                    }
                },
                "leave_days": {
                    "$sum": {
                        "$cond": [{"$eq": ["$status", "LEAVE"]}, 1, 0]
                    }
                },
                "late_count": {
                    "$sum": {
                        "$cond": [
                            {"$gt": [{"$ifNull": ["$late_minutes", 0]}, 0]},
                            1,
                            0
                        ]
                    }
                },
                "total_late_minutes": {
                    "$sum": {"$ifNull": ["$late_minutes", 0]}
                },
                "total_overtime_minutes": {
                    "$sum": {"$ifNull": ["$overtime_minutes", 0]}
                }
            }
        }
    ]))

    agg = records[0] if records else {}
    present = half_up(agg.get("present_days", 0))

    pct = (
        half_up(
            Decimal(str(present)) / Decimal(str(working_days)) * 100,
            2
        )
        if working_days else None
    )

    return {
        "emp_code": emp_code,
        "month": month,
        "working_days": working_days,
        "present_days": present,
        "leave_days": agg.get("leave_days", 0),
        "late_count": agg.get("late_count", 0),
        "total_late_minutes": agg.get("total_late_minutes", 0),
        "total_overtime_minutes": agg.get("total_overtime_minutes", 0),
        "attendance_pct": pct
    }

@app.get("/analytics/departments/summary")
def department_summary(month: str, department: Optional[str] = None):
    first, last = parse_month(month)

    match_emp = {"joined_on": {"$lte": last.isoformat()}}
    if department is not None:
        match_emp["department"] = department

    pipeline = [
        {
            "$match": {
                "date": {
                    "$gte": first.isoformat(),
                    "$lte": last.isoformat()
                }
            }
        },
        {
            "$lookup": {
                "from": "employees",
                "localField": "emp_code",
                "foreignField": "emp_code",
                "as": "employee"
            }
        },
        {"$unwind": "$employee"},
        {
            "$match": {
                "employee.joined_on": {"$lte": last.isoformat()},
                "$expr": {"$gte": ["$date", "$employee.joined_on"]},
                **(
                    {"employee.department": department}
                    if department is not None else {}
                )
            }
        },
        {
            "$group": {
                "_id": "$employee.department",
                "present_days": {
                    "$sum": {
                        "$cond": [
                            {
                                "$and": [
                                    {"$in": ["$status", list(PRESENCE)]},
                                    {
                                        "$in": [
                                            {
                                                "$dayOfWeek": {
                                                    "$dateFromString": {
                                                        "dateString": "$date"
                                                    }
                                                }
                                            },
                                            [2, 3, 4, 5, 6]
                                        ]
                                    }
                                ]
                            },
                            {"$cond": ["$half_day", 0.5, 1]},
                            0
                        ]
                    }
                },
                "hours_sum": {
                    "$sum": {
                        "$cond": [
                            {
                                "$and": [
                                    {"$in": ["$status", list(PRESENCE)]},
                                    {"$ne": ["$work_hours", None]}
                                ]
                            },
                            "$work_hours",
                            0
                        ]
                    }
                },
                "hours_count": {
                    "$sum": {
                        "$cond": [
                            {
                                "$and": [
                                    {"$in": ["$status", list(PRESENCE)]},
                                    {"$ne": ["$work_hours", None]}
                                ]
                            },
                            1,
                            0
                        ]
                    }
                },
                "late_count": {
                    "$sum": {
                        "$cond": [
                            {"$gt": [{"$ifNull": ["$late_minutes", 0]}, 0]},
                            1,
                            0
                        ]
                    }
                },
                "total_late_minutes": {
                    "$sum": {"$ifNull": ["$late_minutes", 0]}
                },
                "leave_count": {
                    "$sum": {
                        "$cond": [{"$eq": ["$status", "LEAVE"]}, 1, 0]
                    }
                },
                "on_duty_count": {
                    "$sum": {
                        "$cond": [{"$eq": ["$status", "ON_DUTY"]}, 1, 0]
                    }
                }
            }
        }
    ]

    log_stats = {
        item["_id"]: item
        for item in db.attendance_logs.aggregate(pipeline)
    }

    roster_pipeline = [
        {"$match": match_emp},
        {
            "$group": {
                "_id": "$department",
                "headcount": {"$sum": 1}
            }
        },
        {"$sort": {"_id": 1}}
    ]

    items = []
    for roster in db.employees.aggregate(roster_pipeline):
        stats = log_stats.get(roster["_id"], {})
        count = stats.get("hours_count", 0)

        items.append({
            "department": roster["_id"],
            "headcount": roster["headcount"],
            "present_days": half_up(stats.get("present_days", 0)),
            "avg_work_hours": (
                half_up(stats["hours_sum"] / count)
                if count else None
            ),
            "late_count": stats.get("late_count", 0),
            "total_late_minutes": stats.get("total_late_minutes", 0),
            "leave_count": stats.get("leave_count", 0),
            "on_duty_count": stats.get("on_duty_count", 0)
        })

    return {"month": month, "items": items}
@app.get("/analytics/leaderboard/late")
def late_leaderboard(
    month: str,
    limit: int = Query(10, ge=1, le=50),
    department: Optional[str] = None
):
    first, last = parse_month(month)

    pipeline = [
        {
            "$match": {
                "date": {
                    "$gte": first.isoformat(),
                    "$lte": last.isoformat()
                },
                "late_minutes": {"$gt": 0}
            }
        },
        {
            "$group": {
                "_id": "$emp_code",
                "total_late_minutes": {"$sum": "$late_minutes"},
                "late_count": {"$sum": 1}
            }
        },
        {
            "$lookup": {
                "from": "employees",
                "localField": "_id",
                "foreignField": "emp_code",
                "as": "employee"
            }
        },
        {"$unwind": "$employee"}
    ]

    if department is not None:
        pipeline.append({
            "$match": {"employee.department": department}
        })

    pipeline += [
        {
            "$sort": {
                "total_late_minutes": -1,
                "_id": 1
            }
        },
        {
            "$setWindowFields": {
                "sortBy": {"total_late_minutes": -1},
                "output": {"rank": {"$rank": {}}}
            }
        },
        {"$match": {"rank": {"$lte": limit}}},
        {
            "$project": {
                "_id": 0,
                "rank": 1,
                "emp_code": "$_id",
                "name": "$employee.name",
                "department": "$employee.department",
                "total_late_minutes": 1,
                "late_count": 1
            }
        }
    ]

    return {
        "month": month,
        "items": list(db.attendance_logs.aggregate(pipeline))
    }
@app.get("/analytics/departments/{department}/trend")
def department_trend(
    department: str,
    from_date: str = Query(alias="from"),
    to_date: str = Query(alias="to")
):
    start = parse_date(from_date, "from")
    end = parse_date(to_date, "to")

    if end < start:
        raise HTTPException(422, "to must be on or after from")

    if (end - start).days + 1 > 92:
        raise HTTPException(422, "Date range must not exceed 92 days")

    if not db.employees.find_one({"department": department}, {"_id": 1}):
        raise HTTPException(404, "Department not found")

    pipeline = [
        {
            "$match": {
                "date": {
                    "$gte": start.isoformat(),
                    "$lte": end.isoformat()
                }
            }
        },
        {
            "$lookup": {
                "from": "employees",
                "localField": "emp_code",
                "foreignField": "emp_code",
                "as": "employee"
            }
        },
        {"$unwind": "$employee"},
        {"$match": {"employee.department": department}},
        {
            "$group": {
                "_id": {"$dateFromString": {"dateString": "$date"}},
                "present_count": {
                    "$sum": {
                        "$cond": [
                            {"$in": ["$status", list(PRESENCE)]},
                            {"$cond": ["$half_day", 0.5, 1]},
                            0
                        ]
                    }
                },
                "late_count": {
                    "$sum": {
                        "$cond": [
                            {"$gt": [{"$ifNull": ["$late_minutes", 0]}, 0]},
                            1,
                            0
                        ]
                    }
                }
            }
        },
        {
            "$project": {
                "_id": 0,
                "date": "$_id",
                "present_count": 1,
                "late_count": 1
            }
        },
        {
            "$densify": {
                "field": "date",
                "range": {
                    "step": 1,
                    "unit": "day",
                    "bounds": [
                        datetime.combine(start, time.min),
                        datetime.combine(end + timedelta(days=1), time.min)
                    ]
                }
            }
        },
        {
            "$set": {
                "is_working_day": {
                    "$in": [{"$dayOfWeek": "$date"}, [2, 3, 4, 5, 6]]
                },
                "present_count": {"$ifNull": ["$present_count", 0]},
                "late_count": {"$ifNull": ["$late_count", 0]}
            }
        },
        {
            "$lookup": {
                "from": "employees",
                "let": {
                    "day": {
                        "$dateToString": {
                            "date": "$date",
                            "format": "%Y-%m-%d"
                        }
                    }
                },
                "pipeline": [
                    {"$match": {"department": department}},
                    {
                        "$match": {
                            "$expr": {"$lte": ["$joined_on", "$$day"]}
                        }
                    },
                    {"$count": "count"}
                ],
                "as": "roster"
            }
        },
        {
            "$set": {
                "headcount": {
                    "$ifNull": [{"$arrayElemAt": ["$roster.count", 0]}, 0]
                }
            }
        },
        {
            "$set": {
                "attendance_rate": {
                    "$cond": [
                        {
                            "$and": [
                                "$is_working_day",
                                {"$gt": ["$headcount", 0]}
                            ]
                        },
                        {
                            "$round": [
                                {
                                    "$multiply": [
                                        {
                                            "$divide": [
                                                "$present_count",
                                                "$headcount"
                                            ]
                                        },
                                        100
                                    ]
                                },
                                4
                            ]
                        },
                        None
                    ]
                }
            }
        },
        {
            "$setWindowFields": {
                "sortBy": {"date": 1},
                "output": {
                    "moving_avg_7d": {
                        "$avg": "$attendance_rate",
                        "window": {"documents": [-6, 0]}
                    }
                }
            }
        },
        {"$sort": {"date": 1}},
        {
            "$set": {
                "date": {
                    "$dateToString": {
                        "date": "$date",
                        "format": "%Y-%m-%d"
                    }
                }
            }
        },
        {
            "$project": {
                "_id": 0,
                "date": 1,
                "is_working_day": 1,
                "headcount": 1,
                "present_count": 1,
                "late_count": 1,
                "attendance_rate": 1,
                "moving_avg_7d": 1
            }
        }
    ]

    rows = list(db.attendance_logs.aggregate(pipeline))

    for row in rows:
        for key in ("present_count", "attendance_rate", "moving_avg_7d"):
            if row.get(key) is not None:
                row[key] = half_up(row[key], 4)

    return {
        "department": department,
        "from": from_date,
        "to": to_date,
        "items": rows
    }
@app.get("/admin/explain/{endpoint}")
def explain_endpoint(
    endpoint: str,
    month: Optional[str] = None,
    emp_code: Optional[str] = None,
    department: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    limit: int = Query(10, ge=1, le=50),
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
):
    allowed = {"attendance_list", "employee_monthly", "department_summary", "late_leaderboard", "department_trend"}
    if endpoint not in allowed:
        raise HTTPException(422, f"endpoint must be one of: {', '.join(sorted(allowed))}")
    if endpoint == "attendance_list":
        start, end = validate_date_range(date_from, date_to)
        q = {}
        if emp_code is not None:
            q["emp_code"] = emp_code
        if start or end:
            q["date"] = {}
            if start:
                q["date"]["$gte"] = start.isoformat()
            if end:
                q["date"]["$lte"] = end.isoformat()
        if status is not None:
            if status not in ALL_STATUSES:
                raise HTTPException(422, "Invalid attendance status")
            q["status"] = status

        explain = db.command(
            "explain",
            {
                "find": "attendance_logs",
                "filter": q,
                "sort": {"date": -1, "emp_code": 1},
                "skip": (page - 1) * page_size,
                "limit": page_size,
            },
            verbosity="executionStats",
        )
        return {
            "endpoint": endpoint,
            "collection": "attendance_logs",
            "explain": explain,
        }
    if endpoint == "employee_monthly":
        if not emp_code or not month:
            raise HTTPException(422, "emp_code and month are required")

        first, last = parse_month(month)

        pipeline = [
            {
                "$match": {
                    "emp_code": emp_code,
                    "date": {
                        "$gte": first.isoformat(),
                        "$lte": last.isoformat(),
                    },
                }
            },
            {
                "$group": {
                    "_id": None,
                    "present_days": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$and": [
                                        {"$in": ["$status", list(PRESENCE)]},
                                        {
                                            "$in": [
                                                {
                                                    "$dayOfWeek": {
                                                        "$dateFromString": {
                                                            "dateString": "$date"
                                                        }
                                                    }
                                                },
                                                [2, 3, 4, 5, 6],
                                            ]
                                        },
                                    ]
                                },
                                {"$cond": ["$half_day", 0.5, 1]},
                                0,
                            ]
                        }
                    },
                    "leave_days": {
                        "$sum": {
                            "$cond": [{"$eq": ["$status", "LEAVE"]}, 1, 0]
                        }
                    },
                    "late_count": {
                        "$sum": {
                            "$cond": [
                                {"$gt": [{"$ifNull": ["$late_minutes", 0]}, 0]},
                                1,
                                0,
                            ]
                        }
                    },
                    "total_late_minutes": {
                        "$sum": {"$ifNull": ["$late_minutes", 0]}
                    },
                    "total_overtime_minutes": {
                        "$sum": {"$ifNull": ["$overtime_minutes", 0]}
                    },
                }
            },
        ]

        explain = db.command(
            "explain",
            {"aggregate": "attendance_logs", "pipeline": pipeline, "cursor": {}},
            verbosity="executionStats",
        )
        return {
            "endpoint": endpoint,
            "collection": "attendance_logs",
            "explain": explain,
        }

    if endpoint == "department_summary":
        if not month:
            raise HTTPException(422, "month is required")

        first, last = parse_month(month)

        match = {
            "date": {
                "$gte": first.isoformat(),
                "$lte": last.isoformat(),
            }
        }

        employee_match = {
            "employee.joined_on": {"$lte": last.isoformat()}
        }
        roster_match = {"joined_on": {"$lte": last.isoformat()}}

        if department is not None:
            employee_match["employee.department"] = department
            roster_match["department"] = department

        pipeline = [
            {"$match": match},
            {
                "$lookup": {
                    "from": "employees",
                    "localField": "emp_code",
                    "foreignField": "emp_code",
                    "as": "employee",
                }
            },
            {"$unwind": "$employee"},
            {"$match": employee_match},
            {
                "$group": {
                    "_id": "$employee.department",
                    "present_days": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$and": [
                                        {"$in": ["$status", list(PRESENCE)]},
                                        {
                                            "$in": [
                                                {
                                                    "$dayOfWeek": {
                                                        "$dateFromString": {
                                                            "dateString": "$date"
                                                        }
                                                    }
                                                },
                                                [2, 3, 4, 5, 6],
                                            ]
                                        },
                                    ]
                                },
                                {"$cond": ["$half_day", 0.5, 1]},
                                0,
                            ]
                        }
                    },
                    "hours_sum": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$and": [
                                        {"$in": ["$status", list(PRESENCE)]},
                                        {"$ne": ["$work_hours", None]},
                                    ]
                                },
                                "$work_hours",
                                0,
                            ]
                        }
                    },
                    "hours_count": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$and": [
                                        {"$in": ["$status", list(PRESENCE)]},
                                        {"$ne": ["$work_hours", None]},
                                    ]
                                },
                                1,
                                0,
                            ]
                        }
                    },
                    "late_count": {
                        "$sum": {
                            "$cond": [
                                {"$gt": [{"$ifNull": ["$late_minutes", 0]}, 0]},
                                1,
                                0,
                            ]
                        }
                    },
                    "total_late_minutes": {
                        "$sum": {"$ifNull": ["$late_minutes", 0]}
                    },
                    "leave_count": {
                        "$sum": {
                            "$cond": [{"$eq": ["$status", "LEAVE"]}, 1, 0]
                        }
                    },
                    "on_duty_count": {
                        "$sum": {
                            "$cond": [{"$eq": ["$status", "ON_DUTY"]}, 1, 0]
                        }
                    },
                }
            },
        ]

        attendance_explain = db.command(
            "explain",
            {
                "aggregate": "attendance_logs",
                "pipeline": pipeline,
                "cursor": {},
            },
            verbosity="executionStats",
        )

        roster_pipeline = [
            {"$match": roster_match},
            {
                "$group": {
                    "_id": "$department",
                    "headcount": {"$sum": 1},
                }
            },
            {"$sort": {"_id": 1}},
        ]

        roster_explain = db.command(
            "explain",
            {
                "aggregate": "employees",
                "pipeline": roster_pipeline,
                "cursor": {},
            },
            verbosity="executionStats",
        )

        return {
            "endpoint": endpoint,
            "collection": ["attendance_logs", "employees"],
            "explain": {
                "attendance": attendance_explain,
                "roster": roster_explain,
            },
        }

    if endpoint == "late_leaderboard":
        if not month:
            raise HTTPException(422, "month is required")

        first, last = parse_month(month)

        pipeline = [
            {
                "$match": {
                    "date": {
                        "$gte": first.isoformat(),
                        "$lte": last.isoformat(),
                    },
                    "late_minutes": {"$gt": 0},
                }
            },
            {
                "$group": {
                    "_id": "$emp_code",
                    "total_late_minutes": {"$sum": "$late_minutes"},
                    "late_count": {"$sum": 1},
                }
            },
            {
                "$lookup": {
                    "from": "employees",
                    "localField": "_id",
                    "foreignField": "emp_code",
                    "as": "employee",
                }
            },
            {"$unwind": "$employee"},
        ]

        if department is not None:
            pipeline.append(
                {"$match": {"employee.department": department}}
            )

        pipeline += [
            {
                "$sort": {
                    "total_late_minutes": -1,
                    "_id": 1,
                }
            },
            {
                "$setWindowFields": {
                    "sortBy": {"total_late_minutes": -1},
                    "output": {"rank": {"$rank": {}}},
                }
            },
            {"$match": {"rank": {"$lte": limit}}},
            {
                "$project": {
                    "_id": 0,
                    "rank": 1,
                    "emp_code": "$_id",
                    "name": "$employee.name",
                    "department": "$employee.department",
                    "total_late_minutes": 1,
                    "late_count": 1,
                }
            },
        ]

        explain = db.command(
            "explain",
            {
                "aggregate": "attendance_logs",
                "pipeline": pipeline,
                "cursor": {},
            },
            verbosity="executionStats",
        )

        return {
            "endpoint": endpoint,
            "collection": ["attendance_logs", "employees"],
            "explain": explain,
        }


    if not department or not from_date or not to_date:
        raise HTTPException(422, "department, from, and to are required")

    start = parse_date(from_date, "from")
    end = parse_date(to_date, "to")

    if end < start or (end - start).days + 1 > 92:
        raise HTTPException(422, "Invalid department trend date range")

    pipeline = [
        {
            "$match": {
                "date": {
                    "$gte": start.isoformat(),
                    "$lte": end.isoformat(),
                }
            }
        },
        {
            "$lookup": {
                "from": "employees",
                "localField": "emp_code",
                "foreignField": "emp_code",
                "as": "employee",
            }
        },
        {"$unwind": "$employee"},
        {"$match": {"employee.department": department}},
        {
            "$group": {
                "_id": {
                    "$dateFromString": {"dateString": "$date"}
                },
                "present_count": {
                    "$sum": {
                        "$cond": [
                            {"$in": ["$status", list(PRESENCE)]},
                            {"$cond": ["$half_day", 0.5, 1]},
                            0,
                        ]
                    }
                },
                "late_count": {
                    "$sum": {
                        "$cond": [
                            {
                                "$gt": [
                                    {"$ifNull": ["$late_minutes", 0]},
                                    0,
                                ]
                            },
                            1,
                            0,
                        ]
                    }
                },
            }
        },
        {
            "$project": {
                "_id": 0,
                "date": "$_id",
                "present_count": 1,
                "late_count": 1,
            }
        },
        {
            "$densify": {
                "field": "date",
                "range": {
                    "step": 1,
                    "unit": "day",
                    "bounds": [
                        datetime.combine(start, time.min),
                        datetime.combine(end + timedelta(days=1), time.min),
                    ],
                },
            }
        },
        {
            "$set": {
                "is_working_day": {
                    "$in": [{"$dayOfWeek": "$date"}, [2, 3, 4, 5, 6]]
                },
                "present_count": {"$ifNull": ["$present_count", 0]},
                "late_count": {"$ifNull": ["$late_count", 0]},
            }
        },
        {
            "$lookup": {
                "from": "employees",
                "let": {
                    "day": {
                        "$dateToString": {
                            "date": "$date",
                            "format": "%Y-%m-%d",
                        }
                    }
                },
                "pipeline": [
                    {"$match": {"department": department}},
                    {
                        "$match": {
                            "$expr": {"$lte": ["$joined_on", "$$day"]}
                        }
                    },
                    {"$count": "count"},
                ],
                "as": "roster",
            }
        },
        {
            "$set": {
                "headcount": {
                    "$ifNull": [{"$arrayElemAt": ["$roster.count", 0]}, 0]
                }
            }
        },
        {
            "$set": {
                "attendance_rate": {
                    "$cond": [
                        {
                            "$and": [
                                "$is_working_day",
                                {"$gt": ["$headcount", 0]},
                            ]
                        },
                        {
                            "$round": [
                                {
                                    "$multiply": [
                                        {
                                            "$divide": [
                                                "$present_count",
                                                "$headcount",
                                            ]
                                        },
                                        100,
                                    ]
                                },
                                4,
                            ]
                        },
                        None,
                    ]
                }
            }
        },
        {
            "$setWindowFields": {
                "sortBy": {"date": 1},
                "output": {
                    "moving_avg_7d": {
                        "$avg": "$attendance_rate",
                        "window": {"documents": [-6, 0]},
                    }
                },
            }
        },
        {"$sort": {"date": 1}},
        {
            "$set": {
                "date": {
                    "$dateToString": {
                        "date": "$date",
                        "format": "%Y-%m-%d",
                    }
                }
            }
        },
        {
            "$project": {
                "_id": 0,
                "date": 1,
                "is_working_day": 1,
                "headcount": 1,
                "present_count": 1,
                "late_count": 1,
                "attendance_rate": 1,
                "moving_avg_7d": 1,
            }
        },
    ]

    explain = db.command(
        "explain",
        {
            "aggregate": "attendance_logs",
            "pipeline": pipeline,
            "cursor": {},
        },
        verbosity="executionStats",
    )

    return {
        "endpoint": endpoint,
        "collection": ["attendance_logs", "employees"],
        "explain": explain,
    }
