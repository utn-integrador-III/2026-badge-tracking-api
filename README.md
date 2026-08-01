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
BADGE_TRACKING_VERIFICATION_BASE_URL=http://127.0.0.1:8000
```

`BADGE_TRACKING_VERIFICATION_BASE_URL` is the public base URL encoded into the
age proof QR codes. Set it to the deployed API URL so scanned codes resolve.

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
  "photoUrl": "https://example.com/profile-photo.png",
  "birthDate": "1992-08-28"
}
```

Allowed roles:

```text
student, professor, staff
```

`institutionalId` is the person's Costa Rican ID number. It must contain exactly
9 digits.

`birthDate` is optional and uses the `YYYY-MM-DD` format. It is never returned by
any endpoint; it is only used to answer age proof checks (see US-05).

## US-02 Authenticate via PIN

Set PIN endpoint:

```http
POST /users/{institutionalId}/pin
```

Example:

```http
POST /users/123456789/pin
```

Example body:

```json
{
  "pin": "281992",
  "pinConfirm": "281992"
}
```

Response:

```json
{
  "message": "PIN set successfully",
  "institutionalId": "123456789",
  "pinSetAt": "2026-06-20T16:20:27.493776+00:00"
}
```

Validate PIN endpoint:

```http
POST /users/{institutionalId}/pin/validate
```

Example:

```http
POST /users/123456789/pin/validate
```

Example body:

```json
{
  "pin": "281992"
}
```

Response:

```json
{
  "valid": true,
  "institutionalId": "123456789",
  "message": "PIN validated successfully"
}
```

PIN rules:

```text
6 numeric digits, no repeated same digit, no sequential number
```

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

## US-05 Share Age Proof via Time-Limited QR

The badge holder generates a QR code that proves only whether they meet an age
threshold. The verifying party scans it and never sees the name, institutional
ID, email, badge code, date of birth, or exact age.

Generate QR endpoint (badge holder, PIN required):

```http
POST /users/{institutionalId}/age-proof-qr
```

Example:

```http
POST /users/123456789/age-proof-qr
```

Example body:

```json
{
  "pin": "281992",
  "minimumAge": 18,
  "expiresInSeconds": 120
}
```

`minimumAge` defaults to `18`. `expiresInSeconds` defaults to `120` and must be
between `30` and `900`.

Response:

```json
{
  "token": "4WrIj3Xp07xTYmi1ndnzyL27sr6-RcNqy81sjXHKyKw",
  "verificationUrl": "http://127.0.0.1:8000/verifications/age-proof/4WrIj3Xp07xTYmi1ndnzyL27sr6-RcNqy81sjXHKyKw",
  "qrCodeImage": "data:image/png;base64,iVBORw0KGgo...",
  "minimumAge": 18,
  "meetsMinimumAge": true,
  "issuedAt": "2026-08-01T11:57:02.291991+00:00",
  "expiresAt": "2026-08-01T11:59:02.291991+00:00",
  "expiresInSeconds": 120
}
```

`qrCodeImage` is a PNG data URI that can be rendered directly in an `<img>` tag.
The QR encodes `verificationUrl`, so scanning it opens the verification endpoint.

Verify QR endpoint (verifying party, no authentication):

```http
GET /verifications/age-proof/{token}
```

Response:

```json
{
  "valid": true,
  "minimumAge": 18,
  "meetsMinimumAge": true,
  "role": "student",
  "badgeStatus": "issued",
  "issuedAt": "2026-08-01T11:57:02.291991+00:00",
  "expiresAt": "2026-08-01T11:59:02.291991+00:00",
  "verifiedAt": "2026-08-01T11:57:02.318383+00:00"
}
```

Rules:

```text
PIN authorizes every share, the QR expires after the requested lifetime,
each QR uses a new single-purpose token stored only as a SHA-256 hash,
the token stays valid for repeated scans until it expires,
and a user without a registered birthDate cannot generate an age proof
```

Error responses:

```text
401 Invalid PIN
404 User not found / badge profile not found
404 Age proof QR code was not found
409 No PIN has been set / no date of birth registered / badge not shareable
410 Age proof QR code has expired
422 Invalid institutional ID or request body
```

## Tests

```bash
python -m pytest
python -m pytest --cov=. --cov-report=term-missing
```
