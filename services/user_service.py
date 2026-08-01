import hashlib
import os
import re
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

import bcrypt
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from database.connection import getDatabase
from models.user import (
    GenerateAgeProofQrRequest,
    RegisterInstitutionalIdentityRequest,
    SetPinRequest,
)
from utils.qr_code import buildQrCodeDataUri


DEFAULT_VERIFICATION_BASE_URL = "http://127.0.0.1:8000"
SHAREABLE_BADGE_STATUSES = frozenset({"issued", "active"})


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


class BirthDateNotSetError(Exception):
    pass


class BadgeNotShareableError(Exception):
    pass


class AgeProofTokenNotFoundError(Exception):
    pass


class AgeProofTokenExpiredError(Exception):
    pass


def _hashPin(pin: str) -> str:
    return bcrypt.hashpw(pin.encode(), bcrypt.gensalt(rounds=12)).decode()


def _verifyPin(pin: str, pinHash: str) -> bool:
    return bcrypt.checkpw(pin.encode(), pinHash.encode())


def _getNextSequence(sequenceName: str) -> int:
    database = getDatabase()
    sequence = database.counters.find_one_and_update(
        {"_id": sequenceName},
        {"$inc": {"value": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return int(sequence["value"])


def _assertValidInstitutionalId(institutionalId: str) -> None:
    if not re.fullmatch(r"\d{9}", institutionalId):
        raise InvalidInstitutionalIdError(
            "Institutional ID must contain exactly 9 digits"
        )


def registerInstitutionalIdentity(
    request: RegisterInstitutionalIdentityRequest,
) -> dict:
    database = getDatabase()
    createdAtDate = datetime.now(timezone.utc)
    createdAt = createdAtDate.isoformat()
    validUntil = (createdAtDate + timedelta(days=365)).isoformat()
    badgeCode = f"BADGE-{request.institutionalId.upper()}-{uuid.uuid4().hex[:8].upper()}"

    existingUser = database.users.find_one(
        {
            "$or": [
                {"email": request.email},
                {"institutional_id": request.institutionalId},
            ]
        },
        {"email": 1, "institutional_id": 1},
    )

    if existingUser:
        if existingUser["email"] == request.email:
            raise DuplicateUserError("Email is already registered")
        raise DuplicateUserError("Institutional ID is already registered")

    userId = _getNextSequence("users")
    badgeId = _getNextSequence("badges")
    userDocument = {
        "id": userId,
        "full_name": request.fullName,
        "email": request.email,
        "role": request.role.value,
        "institutional_id": request.institutionalId,
        "photo_url": request.photoUrl,
        "birth_date": request.birthDate,
        "is_active": True,
        "created_at": createdAt,
        "pin_hash": None,
        "pin_set_at": None,
    }
    badgeDocument = {
        "id": badgeId,
        "user_id": userId,
        "badge_code": badgeCode,
        "status": "issued",
        "issued_at": createdAt,
        "valid_from": createdAt,
        "valid_until": validUntil,
    }

    try:
        database.users.insert_one(userDocument)
        database.badges.insert_one(badgeDocument)
    except DuplicateKeyError as error:
        database.users.delete_one({"id": userId})
        if database.users.find_one({"email": request.email}):
            raise DuplicateUserError("Email is already registered") from error
        if database.users.find_one({"institutional_id": request.institutionalId}):
            raise DuplicateUserError("Institutional ID is already registered") from error
        raise DuplicateUserError("User is already registered") from error

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
    _assertValidInstitutionalId(institutionalId)

    database = getDatabase()
    user = database.users.find_one(
        {"institutional_id": institutionalId},
        {
            "id": 1,
            "full_name": 1,
            "role": 1,
            "institutional_id": 1,
            "photo_url": 1,
        },
    )

    if not user:
        raise UserBadgeProfileNotFoundError("Badge profile was not found")

    badge = database.badges.find_one(
        {"user_id": user["id"]},
        {
            "badge_code": 1,
            "status": 1,
            "issued_at": 1,
            "valid_from": 1,
            "valid_until": 1,
        },
    )

    if not badge:
        raise UserBadgeProfileNotFoundError("Badge profile was not found")

    validFrom = badge.get("valid_from") or badge["issued_at"]
    validUntil = badge.get("valid_until") or calculateDefaultValidUntil(validFrom)

    return {
        "photoUrl": user.get("photo_url"),
        "fullName": user["full_name"],
        "role": user["role"],
        "institutionalId": user["institutional_id"],
        "badgeCode": badge["badge_code"],
        "status": badge["status"],
        "validFrom": validFrom,
        "validUntil": validUntil,
    }


def calculateDefaultValidUntil(validFrom: str) -> str:
    validFromDate = datetime.fromisoformat(validFrom)
    return (validFromDate + timedelta(days=365)).isoformat()


def setUserPin(institutionalId: str, request: SetPinRequest) -> dict:
    _assertValidInstitutionalId(institutionalId)

    if request.pin != request.pinConfirm:
        raise PinMismatchError("PIN and PIN confirmation do not match")

    database = getDatabase()
    user = database.users.find_one(
        {"institutional_id": institutionalId},
        {"institutional_id": 1, "pin_hash": 1, "is_active": 1},
    )

    if not user:
        raise UserNotFoundError("User not found")

    if not user["is_active"]:
        raise UserNotFoundError("User account is not active")

    if user.get("pin_hash") is not None:
        raise PinAlreadySetError(
            "PIN has already been set. Contact support to reset it."
        )

    pinSetAt = datetime.now(timezone.utc).isoformat()
    pinHash = _hashPin(request.pin)
    database.users.update_one(
        {"institutional_id": institutionalId},
        {"$set": {"pin_hash": pinHash, "pin_set_at": pinSetAt}},
    )

    return {
        "message": "PIN set successfully",
        "institutionalId": institutionalId,
        "pinSetAt": pinSetAt,
    }


def validateUserPin(institutionalId: str, pin: str) -> dict:
    _assertValidInstitutionalId(institutionalId)
    _authenticateBadgeHolder(institutionalId, pin)

    return {
        "valid": True,
        "institutionalId": institutionalId,
        "message": "PIN validated successfully",
    }


def getVerificationBaseUrl() -> str:
    baseUrl = os.getenv(
        "BADGE_TRACKING_VERIFICATION_BASE_URL",
        DEFAULT_VERIFICATION_BASE_URL,
    )
    return baseUrl.rstrip("/")


def _hashAgeProofToken(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _calculateAge(birthDate: str, referenceDate: date) -> int:
    parsedBirthDate = date.fromisoformat(birthDate)
    age = referenceDate.year - parsedBirthDate.year

    hasHadBirthdayThisYear = (referenceDate.month, referenceDate.day) >= (
        parsedBirthDate.month,
        parsedBirthDate.day,
    )
    if not hasHadBirthdayThisYear:
        age -= 1

    return age


def _authenticateBadgeHolder(institutionalId: str, pin: str) -> dict[str, Any]:
    database = getDatabase()
    user: dict[str, Any] | None = database.users.find_one(
        {"institutional_id": institutionalId},
        {
            "id": 1,
            "role": 1,
            "birth_date": 1,
            "pin_hash": 1,
            "is_active": 1,
        },
    )

    if not user:
        raise UserNotFoundError("User not found")

    if not user["is_active"]:
        raise UserNotFoundError("User account is not active")

    if user.get("pin_hash") is None:
        raise PinNotSetError(
            "No PIN has been set for this user. Please set a PIN first."
        )

    if not _verifyPin(pin, user["pin_hash"]):
        raise InvalidPinError("Invalid PIN")

    return user


def generateAgeProofQr(
    institutionalId: str,
    request: GenerateAgeProofQrRequest,
) -> dict:
    _assertValidInstitutionalId(institutionalId)

    user = _authenticateBadgeHolder(institutionalId, request.pin)

    if not user.get("birth_date"):
        raise BirthDateNotSetError(
            "No date of birth is registered for this user, so age cannot be proven."
        )

    database = getDatabase()
    badge = database.badges.find_one(
        {"user_id": user["id"]},
        {"status": 1},
    )

    if not badge:
        raise UserBadgeProfileNotFoundError("Badge profile was not found")

    if badge["status"] not in SHAREABLE_BADGE_STATUSES:
        raise BadgeNotShareableError(
            f"Badge status '{badge['status']}' cannot be shared for verification"
        )

    issuedAtDate = datetime.now(timezone.utc)
    expiresAtDate = issuedAtDate + timedelta(seconds=request.expiresInSeconds)
    issuedAt = issuedAtDate.isoformat()
    expiresAt = expiresAtDate.isoformat()

    age = _calculateAge(user["birth_date"], issuedAtDate.date())
    meetsMinimumAge = age >= request.minimumAge

    database.age_proof_tokens.delete_many(
        {"user_id": user["id"], "expires_at": {"$lt": issuedAt}}
    )

    token = secrets.token_urlsafe(32)
    database.age_proof_tokens.insert_one(
        {
            "token_hash": _hashAgeProofToken(token),
            "user_id": user["id"],
            "minimum_age": request.minimumAge,
            "meets_minimum_age": meetsMinimumAge,
            "role": user["role"],
            "badge_status": badge["status"],
            "issued_at": issuedAt,
            "expires_at": expiresAt,
        }
    )

    verificationUrl = f"{getVerificationBaseUrl()}/verifications/age-proof/{token}"

    return {
        "token": token,
        "verificationUrl": verificationUrl,
        "qrCodeImage": buildQrCodeDataUri(verificationUrl),
        "minimumAge": request.minimumAge,
        "meetsMinimumAge": meetsMinimumAge,
        "issuedAt": issuedAt,
        "expiresAt": expiresAt,
        "expiresInSeconds": request.expiresInSeconds,
    }


def verifyAgeProof(token: str) -> dict:
    database = getDatabase()
    ageProof: dict[str, Any] | None = database.age_proof_tokens.find_one(
        {"token_hash": _hashAgeProofToken(token)},
        {
            "minimum_age": 1,
            "meets_minimum_age": 1,
            "role": 1,
            "badge_status": 1,
            "issued_at": 1,
            "expires_at": 1,
        },
    )

    if not ageProof:
        raise AgeProofTokenNotFoundError("Age proof QR code was not found")

    verifiedAtDate = datetime.now(timezone.utc)
    if verifiedAtDate >= datetime.fromisoformat(ageProof["expires_at"]):
        raise AgeProofTokenExpiredError("Age proof QR code has expired")

    return {
        "valid": True,
        "minimumAge": ageProof["minimum_age"],
        "meetsMinimumAge": ageProof["meets_minimum_age"],
        "role": ageProof["role"],
        "badgeStatus": ageProof["badge_status"],
        "issuedAt": ageProof["issued_at"],
        "expiresAt": ageProof["expires_at"],
        "verifiedAt": verifiedAtDate.isoformat(),
    }
