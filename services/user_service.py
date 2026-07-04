import uuid
from contextlib import closing
from datetime import datetime, timedelta, timezone
import re

from database.connection import getConnection
from models.user import RegisterInstitutionalIdentityRequest


class DuplicateUserError(Exception):
    pass


class InvalidInstitutionalIdError(Exception):
    pass


class UserBadgeProfileNotFoundError(Exception):
    pass


def registerInstitutionalIdentity(
    request: RegisterInstitutionalIdentityRequest,
) -> dict:
    createdAtDate = datetime.now(timezone.utc)
    createdAt = createdAtDate.isoformat()
    validUntil = (createdAtDate + timedelta(days=365)).isoformat()
    badgeCode = f"BADGE-{request.institutionalId.upper()}-{uuid.uuid4().hex[:8].upper()}"

    with closing(getConnection()) as connection:
        existingUser = connection.execute(
            """
            SELECT email, institutional_id
            FROM users
            WHERE email = ? OR institutional_id = ?
            """,
            (request.email, request.institutionalId),
        ).fetchone()

        if existingUser:
            if existingUser["email"] == request.email:
                raise DuplicateUserError("Email is already registered")
            raise DuplicateUserError("Institutional ID is already registered")

        with connection:
            userCursor = connection.execute(
                """
                INSERT INTO users (
                    full_name,
                    email,
                    role,
                    institutional_id,
                    photo_url,
                    is_active,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request.fullName,
                    request.email,
                    request.role.value,
                    request.institutionalId,
                    request.photoUrl,
                    1,
                    createdAt,
                ),
            )
            userId = userCursor.lastrowid

            badgeCursor = connection.execute(
                """
                INSERT INTO badges (
                    user_id,
                    badge_code,
                    status,
                    issued_at,
                    valid_from,
                    valid_until
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (userId, badgeCode, "issued", createdAt, createdAt, validUntil),
            )
            badgeId = badgeCursor.lastrowid

    return {
        "message": "User registered successfully",
        "user": {
            "id": userId,
            "fullName": request.fullName,
            "email": request.email,
            "role": request.role.value,
            "institutionalId": request.institutionalId,
            "photoUrl": request.photoUrl,
            "isActive": True,
            "createdAt": createdAt,
        },
        "badge": {
            "id": badgeId,
            "userId": userId,
            "badgeCode": badgeCode,
            "status": "issued",
            "issuedAt": createdAt,
            "validFrom": createdAt,
            "validUntil": validUntil,
        },
    }


def getDigitalBadgeProfile(institutionalId: str) -> dict:
    if not re.fullmatch(r"\d{9}", institutionalId):
        raise InvalidInstitutionalIdError(
            "Institutional ID must contain exactly 9 digits"
        )

    with closing(getConnection()) as connection:
        profile = connection.execute(
            """
            SELECT
                users.full_name,
                users.role,
                users.institutional_id,
                users.photo_url,
                badges.badge_code,
                badges.status,
                badges.issued_at,
                badges.valid_from,
                badges.valid_until
            FROM users
            INNER JOIN badges ON badges.user_id = users.id
            WHERE users.institutional_id = ?
            """,
            (institutionalId,),
        ).fetchone()

    if not profile:
        raise UserBadgeProfileNotFoundError("Badge profile was not found")

    validFrom = profile["valid_from"] or profile["issued_at"]
    validUntil = profile["valid_until"] or calculateDefaultValidUntil(validFrom)

    return {
        "photoUrl": profile["photo_url"],
        "fullName": profile["full_name"],
        "role": profile["role"],
        "institutionalId": profile["institutional_id"],
        "badgeCode": profile["badge_code"],
        "status": profile["status"],
        "validFrom": validFrom,
        "validUntil": validUntil,
    }


def calculateDefaultValidUntil(validFrom: str) -> str:
    validFromDate = datetime.fromisoformat(validFrom)
    return (validFromDate + timedelta(days=365)).isoformat()
