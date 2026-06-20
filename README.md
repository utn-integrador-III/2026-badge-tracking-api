# 2026-badge-tracking-api

Backend API for the Badge Tracking Project.

## Requirements

- Python 3.13+

## Setup

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## Run API

```bash
uvicorn main:app --reload
```

Local URL:

```text
http://127.0.0.1:8000
```

## US-01 Register Institutional Identity

Endpoint:

```http
POST /users/institutional-identities
```

Example body:

```json
{
  "fullName": "Kevin Picado",
  "email": "kevin.picado@utn.ac.cr",
  "role": "student",
  "institutionalId": "123456789"
}
```

Allowed roles:

```text
student, professor, staff
```

`institutionalId` is the person's Costa Rican ID number. It must contain exactly
9 digits.

## Tests

```bash
python -m pytest
python -m pytest --cov=. --cov-report=term-missing
```
