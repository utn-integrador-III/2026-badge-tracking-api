import uuid
from contextlib import closing
from datetime import datetime, timedelta, timezone
import re

import bcrypt

from database.connection import getConnection
from models.user import RegisterInstitutionalIdentityRequest, SetPinRequest


class DuplicateUserError(Exception):
    pass


class InvalidInstitutionalIdError(Exception):
    pass


class UserBadgeProfileNotFoundError(Exception):
    pass


class UserNotFoundError(Exception):
    pass


class PinAlreadySetError(Exception):
    pass


class PinNotSetError(Exception):
    pass


class PinMismatchError(Exception):
    pass


class InvalidPinError(Exception):
    pass


def _hashPin(pin: str) -> str:
    return bcrypt.hashpw(pin.encode(), bcrypt.gensalt(rounds=12)).decode()


def _verifyPin(pin: str, pinHash: str) -> bool:
    return bcrypt.checkpw(pin.encode(), pinHash.encode())


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

def setUserPin(institutionalId: str, request: SetPinRequest) -> dict:
    if not re.fullmatch(r"\d{9}", institutionalId):
        raise InvalidInstitutionalIdError(
            "Institutional ID must contain exactly 9 digits"
        )
 
    if request.pin != request.pinConfirm:
        raise PinMismatchError("PIN and PIN confirmation do not match")
 
    pinSetAt = datetime.now(timezone.utc).isoformat()
    pinHash = _hashPin(request.pin)
 
    with closing(getConnection()) as connection:
        user = connection.execute(
            """
            SELECT id, institutional_id, pin_hash, is_active
            FROM users
            WHERE institutional_id = ?
            """,
            (institutionalId,),
        ).fetchone()
 
        if not user:
            raise UserNotFoundError("User not found")
 
        if not user["is_active"]:
            raise UserNotFoundError("User account is not active")
 
        if user["pin_hash"] is not None:
            raise PinAlreadySetError(
                "PIN has already been set. Contact support to reset it."
            )
 
        with connection:
            connection.execute(
                """
                UPDATE users
                SET pin_hash = ?, pin_set_at = ?
                WHERE institutional_id = ?
                """,
                (pinHash, pinSetAt, institutionalId),
            )
 
    return {
        "message": "PIN set successfully",
        "institutionalId": institutionalId,
        "pinSetAt": pinSetAt,
    }

def validateUserPin(institutionalId: str, pin: str) -> dict:
    if not re.fullmatch(r"\d{9}", institutionalId):
        raise InvalidInstitutionalIdError(
            "Institutional ID must contain exactly 9 digits"
        )
 
    with closing(getConnection()) as connection:
        user = connection.execute(
            """
            SELECT institutional_id, pin_hash, is_active
            FROM users
            WHERE institutional_id = ?
            """,
            (institutionalId,),
        ).fetchone()
 
    if not user:
        raise UserNotFoundError("User not found")
 
    if not user["is_active"]:
        raise UserNotFoundError("User account is not active")
 
    if user["pin_hash"] is None:
        raise PinNotSetError(
            "No PIN has been set for this user. Please set a PIN first."
        )
 
    if not _verifyPin(pin, user["pin_hash"]):
        raise InvalidPinError("Invalid PIN")
 
    return {
        "valid": True,
        "institutionalId": institutionalId,
        "message": "PIN validated successfully",
    }