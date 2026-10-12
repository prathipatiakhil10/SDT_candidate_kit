# Employee Attendance & Analytics API



A REST API built with Python, FastAPI, and MongoDB for employee management, attendance tracking, attendance regularization, and analytics.



## Requirements



- Python 3.11 or newer

- MongoDB 6.0 or newer

- Docker (optional, if running MongoDB in a container)



## Setup



Create and activate a virtual environment:



```powershell

python -m venv .venv

.\\.venv\\Scripts\\Activate.ps1

```



Install dependencies:



```powershell

pip install -r requirements.txt

```



Create a `.env` file in the project root:



```text

MONGO_URI=mongodb://localhost:27017

MONGO_DB=attendance_db

```



### Start MongoDB



Make sure MongoDB is running and reachable at the URI in `.env`.



If you use Docker and do not already have a MongoDB container, you can start one with:



```powershell

docker run -d --name attendance-mongo -p 27017:27017 -v attendance-data:/data/db mongo:7

```



If a container named `attendance-mongo` already exists, start it instead:



```powershell

docker start attendance-mongo

```



### Start the API



```powershell

python -m uvicorn app.main:app --port 8000

```



## API documentation



- Swagger UI: http://127.0.0.1:8000/docs

- Health check: http://127.0.0.1:8000/health



## Project files



- `app/main.py` - API implementation

- `requirements.txt` - Python dependencies

- `openapi.yaml` - API contract

- `DATA_MODEL.md` - MongoDB data model

- `REVIEW.md` - Implementation review

- `DECISIONS.md` - Design decisions

- `sample_data/` - Sample employee and attendance data

- `sample_seed.py` - Sample data loader



## Sample data warning



\*\*Running `python sample_seed.py` deletes the existing documents in the `employees` and `attendance_logs` collections before loading the sample data.\*\* Use a disposable development database, not a database containing data you need to keep.



## Submission notes



Do not commit `.env`, credentials, or other secrets. Review the assignment instructions before publishing the repository.
