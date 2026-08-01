# 2026-badge-tracking-api

Backend API for the Badge Tracking Project.

## Requirements

- Python 3.12+
- MongoDB running locally or a MongoDB connection string

## Setup

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

Required for signed badge verification:

Generate a private key locally:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Set the command output as the value (the placeholder below is intentionally not
a valid key):

```text
BADGE_TRACKING_SIGNING_KEY=<paste-generated-secret-here>
```

Optional environment variables:

```text
BADGE_TRACKING_MONGODB_URI=mongodb://localhost:27017
BADGE_TRACKING_MONGODB_DATABASE=badge_tracking
BADGE_TRACKING_VERIFICATION_BASE_URL=http://127.0.0.1:8000
```

`BADGE_TRACKING_VERIFICATION_BASE_URL` is the public base URL encoded into the
QR codes. Set it to the deployed API URL so scanned codes resolve.

`BADGE_TRACKING_SIGNING_KEY` signs badge verification credentials (US-07). It
must be a private random value containing at least 32 bytes. The API deliberately
has no fallback key: QR generation and verification return `503` when the key is
missing or too short. Anyone holding this key can mint badges that pass
verification. Rotating it invalidates QR codes already issued, which is harmless
because they expire within minutes anyway.

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
student, professor, staff, admin
```

Only an `admin` can issue badges to other users (see US-10).

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

## US-07 Verify a Badge (QR Scan)

The badge holder generates a signed verification QR and chooses which attributes
it discloses. A verifier (security desk, registrar) scans it and receives a
cryptographic pass/fail verdict together with those attributes.

### Generate QR (badge holder, PIN required)

```http
POST /users/{institutionalId}/verification-qr
```

Example body:

```json
{
  "pin": "281992",
  "disclose": ["fullName", "photoUrl", "role"],
  "expiresInSeconds": 120
}
```

Disclosable attributes:

```text
fullName, photoUrl, role, institutionalId, badgeCode
```

`disclose` defaults to `["fullName", "photoUrl", "role"]`, cannot be empty and
cannot repeat a value. `expiresInSeconds` defaults to `120` and must be between
`30` and `900`. Disclosing fewer attributes produces a smaller, easier to scan
QR code. The disclosed `role` is the role type of the issued badge; for legacy
badges without `roleType`, the holder's institutional role is used.

The badge must be active and inside its `validFrom`/`validUntil` period when the
QR is generated. Otherwise, the endpoint returns `409`.

Response:

```json
{
  "token": "eyJhdHQiOns...Q.mS0y7xLbUq8...",
  "verificationUrl": "http://127.0.0.1:8000/verifications/badge/eyJhdHQiOns...",
  "qrCodeImage": "data:image/png;base64,iVBORw0KGgo...",
  "disclosedAttributes": ["fullName", "photoUrl", "role"],
  "issuedAt": "2026-08-01T12:31:35.129776+00:00",
  "expiresAt": "2026-08-01T12:33:35.129776+00:00",
  "expiresInSeconds": 120
}
```

### Scan and verify (verifier, no authentication)

Scanner applications post the raw scanned string, which may be the full URL or
the bare token:

```http
POST /verifications/badge
```

```json
{
  "scannedValue": "http://127.0.0.1:8000/verifications/badge/eyJhdHQiOns..."
}
```

A phone camera that opens the scanned URL directly hits the same check:

```http
GET /verifications/badge/{token}
```

Response:

```json
{
  "result": "pass",
  "signatureValid": true,
  "reasons": [],
  "disclosedAttributes": {
    "fullName": "Kevin Picado",
    "photoUrl": "https://example.com/profile-photo.png",
    "role": "student"
  },
  "badgeStatus": "issued",
  "issuedAt": "2026-08-01T12:31:35.129776+00:00",
  "expiresAt": "2026-08-01T12:33:35.129776+00:00",
  "verifiedAt": "2026-08-01T12:31:35.222674+00:00",
  "verificationId": "a1154bb59a2d4c7d9b920b38b7fc08e6"
}
```

When the signing key is configured, both scan endpoints answer `200` for badge
verdicts. A rejected badge is a business outcome the desk has to display, not a
transport error, so failures come back as `"result": "fail"` with the reasons
filled in:

```json
{
  "result": "fail",
  "signatureValid": false,
  "reasons": ["invalid_signature"],
  "disclosedAttributes": {},
  "badgeStatus": null,
  "issuedAt": null,
  "expiresAt": null,
  "verifiedAt": "2026-08-01T12:31:35.225405+00:00",
  "verificationId": "d9191d39b9be40e8b07d073166726d53"
}
```

Failure reasons:

```text
malformed_token                 scanned value is not a badge credential
invalid_signature               payload was edited or signed with another key
unsupported_credential_version  credential format the API cannot verify
credential_not_yet_valid        credential issue time is still in the future
expired                         QR code is past its expiry
user_not_found                  holder no longer exists
user_inactive                   holder account was deactivated
badge_not_found                 holder has no badge
badge_not_active                badge was revoked or suspended
badge_not_yet_valid             badge validity period has not started
badge_expired                   badge validity period has ended
badge_validity_invalid          badge validity dates are missing or inconsistent
```

`422` is returned only when the request body itself is invalid, for example an
empty `scannedValue`. `503` means the server has no valid signing key configured;
it is an operational error, not a badge verdict.

### How the check works

```text
The QR carries a signed credential: base64url(payload).base64url(HMAC-SHA256)
The payload holds the holder id, issue and expiry timestamps, and the
attributes the holder chose to disclose.
```

- The credential is schema-validated after its signature is checked. Missing
  claims, invalid timestamps, unknown attributes and non-object JSON return a
  controlled `malformed_token` failure rather than an internal server error.
- Attributes are **inside** the signature, so editing the name or role in the QR
  breaks verification instead of fooling the desk.
- Attributes are returned after both the signature and the versioned credential
  schema are valid, alongside either a `pass` or a live-status `fail`. Invalid
  signatures, malformed credentials and unsupported versions return an empty
  object. This preserves the verifier's ability to view the disclosed profile
  while displaying an access denial.
- Signature validity alone is not a pass. Every scan re-reads the holder and
  exact badge from the database and checks its status and validity period, so a
  badge revoked, replaced or expired after QR generation fails even while the
  signature is still valid.
- Every scan is recorded in `badge_verifications` with its own `verificationId`,
  the outcome and the reasons, giving the registrar an audit trail.

The signed payload is base64url-encoded, not encrypted. Anyone holding the QR
can decode the attributes selected by the holder, so clients should disclose
only what the verifier needs and use the shortest practical lifetime. Invalid
or expired QR responses should not be cached by clients. QR generation and
badge-verdict responses include `Cache-Control: no-store` and
`Referrer-Policy: no-referrer`.

This online US-07 flow currently uses HMAC-SHA256. Asymmetric institutional
signatures and offline public-key verification are separate US-20/US-08
architecture work; QR single-use consumption belongs to the US-19 lifecycle.

## US-10 Issue a New Badge to a User

An institutional admin creates a badge record tied to a user, sets its role
type, and triggers issuance to the user's device.

### Issue a badge (admin)

```http
POST /badges
```

Example body:

```json
{
  "adminInstitutionalId": "900000001",
  "adminPin": "481726",
  "institutionalId": "123456789",
  "roleType": "staff",
  "validForDays": 180
}
```

The admin authenticates with their own institutional ID and PIN, and must have
the `admin` role. `roleType` defaults to the holder's institutional role, so an
admin can issue a staff badge to someone registered as a student without
changing who that person is. `validForDays` defaults to `365` and must be
between `1` and `1825`.

Response:

```json
{
  "message": "Badge issued successfully",
  "badge": {
    "id": 3,
    "userId": 2,
    "badgeCode": "BADGE-123456789-47B30953",
    "roleType": "staff",
    "status": "issued",
    "issuedAt": "2026-08-01T13:03:27.300024+00:00",
    "validFrom": "2026-08-01T13:03:27.300024+00:00",
    "validUntil": "2027-01-28T13:03:27.300024+00:00"
  },
  "supersededBadgeId": 2,
  "delivery": {
    "deliveryId": "cd159b62463544c986363533d21d5055",
    "badgeId": 3,
    "badgeCode": "BADGE-123456789-47B30953",
    "roleType": "staff",
    "status": "pending",
    "validFrom": "2026-08-01T13:03:27.300024+00:00",
    "validUntil": "2027-01-28T13:03:27.300024+00:00",
    "triggeredAt": "2026-08-01T13:03:27.300024+00:00",
    "deliveredAt": null
  }
}
```

Error responses:

```text
401 Invalid PIN
403 Only an institutional admin can issue badges
404 User not found (admin) / Badge holder was not found
409 No PIN has been set for the admin
422 Invalid institutional ID, role type or validity period
```

### A user holds several badges over time

Issuing a badge marks the holder's previous active badge as `superseded` and
returns its id as `supersededBadgeId`. Badge records are kept rather than
overwritten, so the history of what was issued to whom stays auditable.

```text
issued      the badge the holder currently carries
superseded  replaced by a newer badge
revoked     withdrawn by the institution
```

Only `issued` badges verify. A verification QR generated from a badge that was
later replaced fails with `badge_not_active` and `badgeStatus: "superseded"`,
because US-07 credentials name the badge they were minted from.

`GET /users/{institutionalId}/badge-profile` shows the newest badge.

### Delivery to the user's device

Issuance triggers a delivery the holder's device collects. The device proves it
belongs to the holder with the PIN.

Fetch what is waiting:

```http
POST /users/{institutionalId}/badge-deliveries/fetch
```

```json
{ "pin": "281992" }
```

Response:

```json
{
  "institutionalId": "123456789",
  "deliveries": [
    {
      "deliveryId": "cd159b62463544c986363533d21d5055",
      "badgeId": 3,
      "badgeCode": "BADGE-123456789-47B30953",
      "roleType": "staff",
      "status": "pending",
      "validFrom": "2026-08-01T13:03:27.300024+00:00",
      "validUntil": "2027-01-28T13:03:27.300024+00:00",
      "triggeredAt": "2026-08-01T13:03:27.300024+00:00",
      "deliveredAt": null
    }
  ]
}
```

Confirm installation:

```http
POST /users/{institutionalId}/badge-deliveries/{deliveryId}/acknowledge
```

```json
{ "pin": "281992" }
```

The delivery moves to `delivered` with a `deliveredAt` timestamp and stops
appearing in fetches. Acknowledging twice is safe and keeps the original
delivery time.

Delivery statuses:

```text
pending     triggered, waiting for the device to collect it
delivered   the device confirmed it installed the badge
superseded  replaced by a newer badge before the device collected it
```

Registration also triggers a delivery for the badge it issues, so the first
badge reaches the device through the same path as every later one.

## Tests

```bash
python -m pytest
python -m pytest tests -v --cov=models --cov=routes --cov=services --cov=database --cov=utils --cov-branch --cov-report=term-missing --cov-fail-under=80
```
