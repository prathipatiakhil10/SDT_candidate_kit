# Employee Attendance & Analytics API



A REST API built with Python, FastAPI, and MongoDB for employee management, attendance tracking, attendance regularization, and analytics.



## Requirements



\- Python 3.11 or newer

\- MongoDB 6.0 or newer



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



Create a `.env` file in the project root with your local MongoDB settings:



```text

MONGO_URI=mongodb://localhost:27017

MONGO_DB=attendance\_db

```



Make sure MongoDB is running, then start the API:



```powershell

python -m uvicorn app.main:app --port 8000

```



## API documentation



\- Swagger UI: http://127.0.0.1:8000/docs

\- Health check: http://127.0.0.1:8000/health



## Project files



\- `app/main.py` - API implementation

\- `requirements.txt` - Python dependencies

\- `openapi.yaml` - API contract

\- `DATA_MODEL.md` - MongoDB data model

\- `REVIEW.md` - Implementation review

\- `DECISIONS.md` - Design decisions

\- `sample_data/` - Sample employee and attendance data

\- `sample_seed.py` - Sample data loader



## Submission notes



Do not commit `.env`, credentials, or other secrets. Review the assignment instructions before publishing the repository.
