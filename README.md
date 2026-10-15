# Employee Attendance & Analytics API

A REST API built with Python, FastAPI, and MongoDB for employee management, attendance tracking, attendance corrections, and analytics.

## Tech Stack

- Python 3.11+
- FastAPI
- PyMongo
- MongoDB 6.0+
- Pydantic
- Uvicorn

## Features

- Employee creation and listing
- Attendance punch-in and punch-out
- Attendance listing with filtering and pagination
- Attendance correction with validation and audit history
- Monthly employee attendance analytics
- Department attendance summaries
- Late-arrival leaderboard with tie-aware ranking
- Department daily trends with a seven-day moving average
- MongoDB query-plan inspection through explain endpoints
- Health-check endpoint

## Prerequisites

- Python 3.11 or newer
- MongoDB 6.0 or newer
- Git

## Setup

Open a terminal in the project directory.

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```env
MONGO_URI=mongodb://localhost:27017
MONGO_DB=attendance_db
```

Use your own MongoDB connection URI if MongoDB is running elsewhere. Keep `.env` private and never commit credentials.
## Start MongoDB

Make sure MongoDB 6.0 or newer is running and reachable at the URI configured in `.env`.

If using Docker and a MongoDB container does not already exist, create one with:

```powershell
docker run -d --name attendance-mongo -p 27017:27017 -v attendance-data:/data/db mongo:7
```

If the `attendance-mongo` container already exists but is stopped, start it with:

```powershell
docker start attendance-mongo
```

Use your own MongoDB connection URI if MongoDB is running elsewhere.

## Sample Data Warning

**Running `python sample_seed.py` deletes the existing documents in the `employees` and `attendance_logs` collections before loading sample data.** Use a disposable development database, not a database containing data you need to keep.


## Run the API

```powershell
python -m uvicorn app.main:app --port 8000
```

Open the interactive API documentation:

- Swagger UI: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/health

The application creates its required MongoDB indexes during startup.

## API Endpoints

- `GET /health`
- `POST /employees`
- `GET /employees`
- `POST /attendance/punch-in`
- `GET /attendance`
- `POST /attendance/punch-out`
- `PATCH /attendance/{emp_code}/{date}`
- `GET /analytics/employees/{emp_code}/monthly`
- `GET /analytics/departments/summary`
- `GET /analytics/leaderboard/late`
- `GET /analytics/departments/{department}/trend`
- `GET /admin/explain/{endpoint}`

Refer to Swagger UI for request parameters, request bodies, and response schemas.

## Data and Time Handling

- API timestamps use epoch milliseconds.
- Attendance timestamps are stored in MongoDB as UTC datetimes.
- Calendar dates and monthly reporting follow Indian Standard Time (IST).
- MongoDB's internal `_id` field is excluded from API responses.

## Documentation

- `REVIEW.md` documents defects identified in the starter implementation, their symptoms, and fixes.
- `DECISIONS.md` explains indexing, concurrency, leaderboard ties, headcount, and scaling decisions.

## Security and Configuration

- Database configuration is read from environment variables.
- Do not commit `.env`, secrets, virtual environments, or database dumps.
- The API requires MongoDB to be reachable at startup.

## Testing

Compile-check the main application module:

```powershell
python -m py_compile .\app\main.py
```

The API was manually checked using Swagger UI. The health endpoint, employee and attendance listing endpoints, selected analytics endpoints, and explain endpoint variants returned HTTP 200 when valid parameters were supplied.

No automated test suite was present in the project directory during verification. Manual HTTP success responses do not establish that every business rule or concurrency scenario has been tested.

Open Swagger UI at http://127.0.0.1:8000/docs to exercise the endpoints and inspect their request and response schemas.
