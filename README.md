# 2026-badge-tracking-api

Backend API for the Badge Tracking Project.

## Requirements

- Python 3.13+
- MongoDB running locally or a MongoDB connection string

## Setup

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

Optional environment variables:

```text
BADGE_TRACKING_MONGODB_URI=mongodb://localhost:27017
BADGE_TRACKING_MONGODB_DATABASE=badge_tracking
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
  "institutionalId": "123456789",
  "photoUrl": "https://example.com/profile-photo.png"
}
```

Allowed roles:

```text
student, professor, staff
```

`institutionalId` is the person's Costa Rican ID number. It must contain exactly
9 digits.

## US-03 View My Digital Badge Profile

Endpoint:

```http
GET /users/{institutionalId}/badge-profile
```

Example:

```http
GET /users/123456789/badge-profile
```

Response:

```json
{
  "photoUrl": "https://example.com/profile-photo.png",
  "fullName": "Kevin Picado",
  "role": "student",
  "institutionalId": "123456789",
  "badgeCode": "BADGE-123456789-ABC12345",
  "status": "issued",
  "validFrom": "2026-06-20T16:20:27.493776+00:00",
  "validUntil": "2027-06-20T16:20:27.493776+00:00"
}
```

## Tests

```bash
python -m pytest
python -m pytest --cov=. --cov-report=term-missing
```
