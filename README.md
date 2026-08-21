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
BADGE_TRACKING_SIGNING_KEY=change-me-in-every-deployed-environment
BADGE_TRACKING_ISSUING_AUTHORITY=Universidad Técnica Nacional
```

`BADGE_TRACKING_VERIFICATION_BASE_URL` is the public base URL encoded into the
QR codes. Set it to the deployed API URL so scanned codes resolve.

`BADGE_TRACKING_SIGNING_KEY` signs badge verification credentials (US-07). It
falls back to a well-known development value, so **it must be set to a private
random value in every deployed environment**. Anyone holding this key can mint
badges that pass verification. Rotating it invalidates QR codes already issued,
which is harmless because they expire within minutes anyway.

`BADGE_TRACKING_ISSUING_AUTHORITY` is stored with every badge when it is issued.
It defaults to `Universidad Técnica Nacional`. Changing the setting affects new
badges without rewriting the authority recorded on existing credentials.

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
  "birthDate": "1992-08-28",
  "nationality": "Costa Rican",
  "birthplace": "San Jose, Costa Rica",
  "documentExpiry": "2031-05-20",
  "digitalSignatureUrl": "https://identity.utn.ac.cr/signatures/123456789.png"
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

`nationality`, `birthplace`, and `documentExpiry` are optional for compatibility
with existing identities. `documentExpiry` is the expiry date of the holder's
physical identity document and uses `YYYY-MM-DD`; it is separate from the badge
validity period.

`digitalSignatureUrl` is optional and points to the holder's enrolled visual
signature. It must use HTTPS, cannot contain URL credentials, and is limited to
2,048 characters. Blank values are stored as `null`.

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
QR code.

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

Both endpoints always answer `200`. A rejected badge is a business outcome the
desk has to display, not a transport error, so failures come back as
`"result": "fail"` with the reasons filled in:

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
expired                         QR code is past its expiry
user_not_found                  holder no longer exists
user_inactive                   holder account was deactivated
badge_not_found                 holder has no badge
badge_not_active                badge was revoked or suspended
```

`422` is returned only when the request body itself is invalid, for example an
empty `scannedValue`.

### How the check works

```text
The QR carries a signed credential: base64url(payload).base64url(HMAC-SHA256)
The payload holds the holder id, issue and expiry timestamps, and the
attributes the holder chose to disclose.
```

- Attributes are **inside** the signature, so editing the name or role in the QR
  breaks verification instead of fooling the desk.
- Attributes are returned **only when the signature is valid**. An unverified
  payload is never echoed back, so a forged QR cannot put a name on the screen.
- Signature validity alone is not a pass. Every scan re-reads the holder and
  badge from the database, so a badge revoked after the QR was generated fails
  even while the signature is still valid.
- Every scan is recorded in `badge_verifications` with its own `verificationId`,
  the outcome and the reasons, giving the registrar an audit trail.

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
active      legacy value for a current badge
suspended   temporarily disabled by the institution
superseded  replaced by a newer badge
revoked     permanently withdrawn by the institution
```

Only `issued` badges and legacy `active` badges verify. A verification QR
generated from a badge that was later suspended, revoked or replaced fails with
`badge_not_active`, because US-07 credentials name the exact badge they were
minted from.

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
cancelled   suspended or revoked before the device collected it
```

Registration also triggers a delivery for the badge it issues, so the first
badge reaches the device through the same path as every later one.

## US-11 Revoke or Suspend a Badge

An institutional admin can find a badge holder and suspend or permanently
revoke a specific badge. Both actions take effect immediately while preserving
the badge record and its status history for audit purposes.

### Search for a badge holder (admin)

Endpoint:

```http
POST /badges/search
```

Example body:

```json
{
  "adminInstitutionalId": "900000001",
  "adminPin": "481726",
  "query": "123456789",
  "limit": 20
}
```

`query` accepts an institutional ID, full name or email. Name and email matches
are case-insensitive, and special regular-expression characters are treated as
literal text. The query must contain between `2` and `150` characters after
trimming. `limit` defaults to `20` and must be between `1` and `50`.

Response:

```json
{
  "count": 1,
  "results": [
    {
      "userId": 2,
      "fullName": "Kevin Picado",
      "email": "kevin.picado@utn.ac.cr",
      "institutionalId": "123456789",
      "role": "student",
      "isActive": true,
      "badge": {
        "id": 2,
        "userId": 2,
        "badgeCode": "BADGE-123456789-ABC12345",
        "roleType": "student",
        "status": "issued",
        "issuedAt": "2026-08-01T13:03:27.300024+00:00",
        "validFrom": "2026-08-01T13:03:27.300024+00:00",
        "validUntil": "2027-08-01T13:03:27.300024+00:00"
      }
    }
  ]
}
```

A matching user without a badge is returned with `"badge": null`. A search
with no matches returns `200 OK` with `count: 0` and an empty `results` list.

### Change a badge status (admin)

The path identifies the exact badge to change, which avoids affecting another
badge that may have been issued to the same holder.

```http
PATCH /badges/{badgeId}/status
```

Example:

```http
PATCH /badges/2/status
```

```json
{
  "adminInstitutionalId": "900000001",
  "adminPin": "481726",
  "status": "revoked",
  "reason": "Graduation completed"
}
```

`status` accepts only `suspended` or `revoked`. `reason` is required, is trimmed
before storage and must contain between `3` and `250` characters.

Response:

```json
{
  "message": "Badge revoked successfully",
  "badge": {
    "id": 2,
    "userId": 2,
    "badgeCode": "BADGE-123456789-ABC12345",
    "roleType": "student",
    "status": "revoked",
    "issuedAt": "2026-08-01T13:03:27.300024+00:00",
    "validFrom": "2026-08-01T13:03:27.300024+00:00",
    "validUntil": "2027-08-01T13:03:27.300024+00:00"
  },
  "previousStatus": "issued",
  "changed": true,
  "changedAt": "2026-08-01T15:42:10.184233+00:00",
  "reason": "Graduation completed"
}
```

Allowed transitions:

```text
issued or active  -> suspended or revoked
suspended         -> revoked
revoked           -> terminal; it cannot return to suspended
superseded        -> terminal; it cannot be suspended or revoked
```

Repeating the same requested status is idempotent. It returns `200 OK` with
`changed: false` and preserves the timestamp, reason and audit data from the
original change instead of creating another transition.

Both endpoints authenticate the admin using their institutional ID and PIN and
require the `admin` role and a current badge. Revoking or suspending an admin's
badge therefore removes their badge-management access. The status update records
the previous and new status, UTC timestamp, reason and internal ID of the admin
who performed it. Actual transitions are retained in the badge status history.
The holder identity stays active, so the institution can issue a new badge later
without altering the historical record.

The current prototype creates admin identities through the shared registration
flow. A production deployment must restrict admin-role provisioning and initial
PIN enrollment to a trusted institutional process.

Suspension and revocation immediately affect every verification path:

```text
existing signed badge QR  returns fail with badge_not_active
existing age-proof QR     returns valid: false with the current badge status
new QR or age proof       is rejected while the badge is inactive
pending device delivery   moves to cancelled and is no longer returned to the device
```

Delivered records remain available as history. Only pending deliveries tied to
the affected badge are cancelled.

Age-proof tokens created before this version do not contain a badge ID and fail
closed until they expire. Their maximum lifetime is 15 minutes.

Error responses:

```text
401 Invalid admin PIN
403 The authenticated user is not an active institutional admin
404 Admin user or target badge was not found
409 The admin has no PIN / the requested status transition is not allowed
422 Invalid badge id, institutional ID, query, limit, status or reason
```

## US-15 Display Extended Identity Info

A badge holder can open the credential detail view to see the complete display
information for their newest badge. Extended identity data is protected by the
holder's PIN and is not added to the public badge summary.

### View credential details

```http
POST /users/{institutionalId}/badge-profile/details
```

Example:

```http
POST /users/123456789/badge-profile/details
```

```json
{
  "pin": "281992"
}
```

Response:

```json
{
  "photoUrl": "https://example.com/profile-photo.png",
  "fullName": "Kevin Picado",
  "role": "student",
  "institutionalId": "123456789",
  "badgeCode": "BADGE-123456789-47B30953",
  "roleType": "student",
  "status": "issued",
  "validFrom": "2026-08-07T15:10:00.000000+00:00",
  "validUntil": "2027-08-07T15:10:00.000000+00:00",
  "issuedAt": "2026-08-07T15:10:00.000000+00:00",
  "issuingAuthority": "Universidad Técnica Nacional",
  "nationality": "Costa Rican",
  "birthplace": "San Jose, Costa Rica",
  "documentExpiry": "2031-05-20",
  "digitalSignatureUrl": "https://identity.utn.ac.cr/signatures/123456789.png"
}
```

`issuedAt` and `issuingAuthority` belong to the badge record. Reissuing a badge
therefore displays the date and authority captured for the new credential rather
than values from the badge it replaced. The issuing authority is read from
`BADGE_TRACKING_ISSUING_AUTHORITY` when each badge is created.

`nationality`, `birthplace`, and `documentExpiry` belong to the institutional
identity. Existing records without these attributes return `null`. Older badge
records without an authority use the currently configured authority as a
compatibility fallback.

The public `GET /users/{institutionalId}/badge-profile` response remains a
summary and does not include the extended identity attributes. Successful detail
responses use `Cache-Control: no-store`, `Pragma: no-cache`, and
`Referrer-Policy: no-referrer` so credential data is not retained by shared
caches.

Error responses:

```text
401 Invalid PIN
404 User not found / User account is not active / Badge profile was not found
409 No PIN has been set for this user
422 Invalid institutional ID, PIN format, or document expiry format
```

## US-16 Display Digital Signature

The authenticated credential details response includes the holder's enrolled
visual signature in `digitalSignatureUrl`. The value belongs to the institutional
identity and remains available when the holder receives a reissued badge.

```http
POST /users/{institutionalId}/badge-profile/details
```

```json
{
  "pin": "281992"
}
```

Relevant response field:

```json
{
  "digitalSignatureUrl": "https://identity.utn.ac.cr/signatures/123456789.png"
}
```

Existing identities without an enrolled signature return
`"digitalSignatureUrl": null`. The field is excluded from registration responses
and the public badge profile. The credential details endpoint continues to use
PIN authentication and no-store response headers.

This visual signature is distinct from the cryptographic signature used to
detect credential tampering. `digitalSignatureUrl` is display content and must
not be treated as proof that a badge or QR payload is authentic.

Signature URLs are validated when the institutional identity is registered:

```text
HTTPS is required
embedded username or password values are rejected
the maximum length is 2,048 characters after trimming
blank or omitted values are stored as null
```

## US-14 Expiry and Renewal Notifications

Thirty days before a badge expires, its holder gets a notification carrying a
renewal call to action. The notice is queued once per badge and waits in the
holder's device queue until it is collected, acted on, or the badge changes.

### Queue the notices (scheduled job)

```bash
python -m jobs.expiry_notifications
```

The job walks every active badge that entered the expiry window and queues the
notice for its holder, so a holder is warned even when their device has not
opened the app for weeks. Running it twice never warns anybody twice. Schedule
it once a day.

Fetching notifications also evaluates the caller's own badge, so a device that
syncs between two job runs still sees the notice on time.

### Collect the notifications (badge holder, PIN required)

```http
POST /users/{institutionalId}/badge-notifications/fetch
```

```json
{ "pin": "281992" }
```

Response:

```json
{
  "institutionalId": "123456789",
  "notifications": [
    {
      "notificationId": "8f0b1d4c9a1c4f0e9a4c2b7d5e6f1a30",
      "type": "badge_expiring",
      "status": "pending",
      "badgeId": 3,
      "badgeCode": "BADGE-123456789-47B30953",
      "title": "Your badge expires in 30 days",
      "body": "Badge BADGE-123456789-47B30953 expires in 30 days on 2027-01-28. Request a renewal to keep using your digital badge.",
      "actionLabel": "Renew badge",
      "actionUrl": "http://127.0.0.1:8000/users/123456789/badge-renewals",
      "daysUntilExpiry": 30,
      "expired": false,
      "validUntil": "2027-01-28T13:03:27.300024+00:00",
      "createdAt": "2026-12-29T13:03:27.300024+00:00",
      "deliveredAt": null
    }
  ]
}
```

`daysUntilExpiry`, `title` and `body` are built when the device syncs, never
when the notice was queued, so a notification that waited in the queue still
shows an accurate countdown. Once the expiry date passes, the same notification
reports `"expired": true` and asks for a renewal instead of counting down.

Confirm the push reached the device:

```http
POST /users/{institutionalId}/badge-notifications/{notificationId}/acknowledge
```

Clear it from the holder's device:

```http
POST /users/{institutionalId}/badge-notifications/{notificationId}/dismiss
```

Both take `{ "pin": "281992" }`. Acknowledging moves the notice to `delivered`
with a `deliveredAt` timestamp and stops it appearing in fetches; repeating
either call is safe and keeps the original timestamps.

Notification statuses:

```text
pending     queued, waiting for the device to collect it
delivered   the device confirmed it showed the notification
dismissed   the holder cleared it or acted on the renewal CTA
resolved    the badge was renewed, suspended or revoked
```

### Renew the badge (the call to action)

`actionUrl` points at the renewal endpoint the CTA calls:

```http
POST /users/{institutionalId}/badge-renewals
```

```json
{ "pin": "281992" }
```

Response:

```json
{
  "requestId": "b74e2c1f88f6446da5d5ec3ff6a01c2b",
  "badgeId": 3,
  "badgeCode": "BADGE-123456789-47B30953",
  "status": "requested",
  "validUntil": "2027-01-28T13:03:27.300024+00:00",
  "daysUntilExpiry": 30,
  "requestedAt": "2026-12-29T13:05:11.482233+00:00",
  "fulfilledAt": null,
  "fulfilledBadgeId": null
}
```

Requesting a renewal dismisses the notification that asked for it, so the
holder stops being nagged while the request is open. Tapping the CTA twice
returns the same open request rather than creating a second one. A holder
whose badge is already suspended or revoked has nothing to renew and gets
`409`.

The request is fulfilled by the existing issuance endpoint: when an admin
issues a new badge for that holder (`POST /badges`, US-10), the open request
moves to `fulfilled` with the new badge in `fulfilledBadgeId`, and the notice
for the replaced badge is resolved. Suspending or revoking a badge cancels its
open renewal request and resolves its notice, alongside the delivery
cancellation described in US-11.

Renewal request statuses:

```text
requested   the holder asked for a renewal
fulfilled   an admin issued the replacement badge
cancelled   the badge was suspended or revoked before renewal
```

### Configuration

```text
BADGE_TRACKING_EXPIRY_NOTICE_DAYS       days of warning before expiry, default 30
BADGE_TRACKING_VERIFICATION_BASE_URL    base URL the renewal actionUrl points at
```

Values outside 1-365, or values that are not whole numbers, fall back to 30
days. Badges predating the validity fields fall back to the same 365-day
default used elsewhere, so legacy holders are warned too.

## Tests

```bash
python -m pytest
python -m pytest --cov=. --cov-report=term-missing
```
