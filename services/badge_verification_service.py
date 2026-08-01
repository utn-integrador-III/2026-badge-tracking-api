import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import ValidationError

from database.connection import getDatabase
from models.user import (
    BadgeVerificationCredential,
    BadgeVerificationResult,
    DisclosableAttribute,
    GenerateBadgeVerificationQrRequest,
    UserRole,
)
from services.user_service import (
    ACTIVE_BADGE_STATUSES,
    BadgeNotShareableError,
    UserBadgeProfileNotFoundError,
    assertValidInstitutionalId,
    authenticateBadgeHolder,
    findLatestBadge,
    getVerificationBaseUrl,
)
from utils.qr_code import buildQrCodeDataUri
from utils.signing import (
    InvalidSignatureError,
    MalformedPayloadError,
    MalformedTokenError,
    readSignedPayload,
    signPayload,
)


BADGE_VERIFICATION_PATH = "/verifications/badge/"
CREDENTIAL_VERSION = 1

REASON_MALFORMED_TOKEN = "malformed_token"
REASON_INVALID_SIGNATURE = "invalid_signature"
REASON_UNSUPPORTED_VERSION = "unsupported_credential_version"
REASON_CREDENTIAL_NOT_YET_VALID = "credential_not_yet_valid"
REASON_EXPIRED = "expired"
REASON_USER_NOT_FOUND = "user_not_found"
REASON_USER_INACTIVE = "user_inactive"
REASON_BADGE_NOT_FOUND = "badge_not_found"
REASON_BADGE_NOT_ACTIVE = "badge_not_active"
REASON_BADGE_NOT_YET_VALID = "badge_not_yet_valid"
REASON_BADGE_EXPIRED = "badge_expired"
REASON_BADGE_VALIDITY_INVALID = "badge_validity_invalid"


def _collectDisclosedAttributes(
    user: dict[str, Any],
    badge: dict[str, Any],
    disclose: list[DisclosableAttribute],
) -> dict[str, str | None]:
    badgeRoleValue = badge.get("role_type") or user["role"]
    try:
        badgeRole = UserRole(badgeRoleValue).value
    except (TypeError, ValueError) as error:
        raise BadgeNotShareableError("Badge role type is invalid") from error

    availableAttributes: dict[DisclosableAttribute, str | None] = {
        DisclosableAttribute.fullName: user["full_name"],
        DisclosableAttribute.photoUrl: user.get("photo_url"),
        DisclosableAttribute.role: badgeRole,
        DisclosableAttribute.institutionalId: user["institutional_id"],
        DisclosableAttribute.badgeCode: badge["badge_code"],
    }

    return {
        attribute.value: availableAttributes[attribute] for attribute in disclose
    }


def _parseStoredTimestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None

    try:
        parsedValue = datetime.fromisoformat(value)
    except ValueError:
        return None

    if parsedValue.tzinfo is None or parsedValue.utcoffset() is None:
        return None

    return parsedValue


def _getBadgeValidityReasons(
    badge: dict[str, Any],
    checkedAt: datetime,
) -> list[str]:
    validFrom = _parseStoredTimestamp(badge.get("valid_from"))
    validUntil = _parseStoredTimestamp(badge.get("valid_until"))

    if validFrom is None or validUntil is None or validUntil <= validFrom:
        return [REASON_BADGE_VALIDITY_INVALID]

    if checkedAt < validFrom:
        return [REASON_BADGE_NOT_YET_VALID]

    if checkedAt >= validUntil:
        return [REASON_BADGE_EXPIRED]

    return []


def generateBadgeVerificationQr(
    institutionalId: str,
    request: GenerateBadgeVerificationQrRequest,
) -> dict:
    assertValidInstitutionalId(institutionalId)

    user = authenticateBadgeHolder(institutionalId, request.pin)

    badge = findLatestBadge(
        user["id"],
        {
            "id": 1,
            "badge_code": 1,
            "role_type": 1,
            "status": 1,
            "valid_from": 1,
            "valid_until": 1,
        },
    )

    if not badge:
        raise UserBadgeProfileNotFoundError("Badge profile was not found")

    badgeStatus = badge.get("status")
    if badgeStatus not in ACTIVE_BADGE_STATUSES:
        raise BadgeNotShareableError(
            f"Badge status '{badgeStatus}' cannot be shared for verification"
        )

    issuedAtDate = datetime.now(timezone.utc)
    validityReasons = _getBadgeValidityReasons(badge, issuedAtDate)
    if validityReasons:
        raise BadgeNotShareableError(
            f"Badge cannot be shared: {validityReasons[0]}"
        )

    expiresAtDate = issuedAtDate + timedelta(seconds=request.expiresInSeconds)
    issuedAt = issuedAtDate.isoformat()
    expiresAt = expiresAtDate.isoformat()

    disclosedAttributes = _collectDisclosedAttributes(user, badge, request.disclose)
    token = signPayload(
        {
            "v": CREDENTIAL_VERSION,
            "uid": user["id"],
            "bid": badge["id"],
            "iat": issuedAt,
            "exp": expiresAt,
            "att": disclosedAttributes,
        }
    )
    verificationUrl = f"{getVerificationBaseUrl()}{BADGE_VERIFICATION_PATH}{token}"

    return {
        "token": token,
        "verificationUrl": verificationUrl,
        "qrCodeImage": buildQrCodeDataUri(verificationUrl),
        "disclosedAttributes": list(request.disclose),
        "issuedAt": issuedAt,
        "expiresAt": expiresAt,
        "expiresInSeconds": request.expiresInSeconds,
    }


def extractScannedToken(scannedValue: str) -> str:
    cleanedValue = scannedValue.strip()

    markerIndex = cleanedValue.rfind(BADGE_VERIFICATION_PATH)
    if markerIndex != -1:
        cleanedValue = cleanedValue[markerIndex + len(BADGE_VERIFICATION_PATH) :]

    return cleanedValue.split("?")[0].split("#")[0]


def _checkLiveBadgeStatus(
    userId: int,
    badgeId: int,
    checkedAt: datetime,
) -> tuple[list[str], str | None]:
    database = getDatabase()
    user = database.users.find_one({"id": userId}, {"is_active": 1})

    if not user:
        return [REASON_USER_NOT_FOUND], None

    if user.get("is_active") is not True:
        return [REASON_USER_INACTIVE], None

    # The credential names the badge it was minted from, so reissuing a badge
    # retires the QR codes of the badge it replaced.
    badge = database.badges.find_one(
        {"id": badgeId, "user_id": userId},
        {
            "status": 1,
            "valid_from": 1,
            "valid_until": 1,
        },
    )

    if not badge:
        return [REASON_BADGE_NOT_FOUND], None

    badgeStatus = badge.get("status")
    if badgeStatus not in ACTIVE_BADGE_STATUSES:
        return [REASON_BADGE_NOT_ACTIVE], badgeStatus

    validityReasons = _getBadgeValidityReasons(badge, checkedAt)
    if validityReasons:
        return validityReasons, badgeStatus

    return [], badgeStatus


def _recordVerification(
    verificationId: str,
    userId: Any,
    result: str,
    reasons: list[str],
    verifiedAt: str,
) -> None:
    getDatabase().badge_verifications.insert_one(
        {
            "verification_id": verificationId,
            "user_id": userId,
            "result": result,
            "reasons": reasons,
            "verified_at": verifiedAt,
        }
    )


def _buildVerificationResponse(
    reasons: list[str],
    signatureValid: bool,
    verificationId: str,
    verifiedAt: str,
    disclosedAttributes: dict[str, str | None] | None = None,
    badgeStatus: str | None = None,
    issuedAt: str | None = None,
    expiresAt: str | None = None,
) -> dict:
    result = (
        BadgeVerificationResult.passed.value
        if not reasons
        else BadgeVerificationResult.failed.value
    )

    return {
        "result": result,
        "signatureValid": signatureValid,
        "reasons": reasons,
        "disclosedAttributes": disclosedAttributes or {},
        "badgeStatus": badgeStatus,
        "issuedAt": issuedAt,
        "expiresAt": expiresAt,
        "verifiedAt": verifiedAt,
        "verificationId": verificationId,
    }


def verifyScannedBadge(scannedValue: str) -> dict:
    verifiedAtDate = datetime.now(timezone.utc)
    verifiedAt = verifiedAtDate.isoformat()
    verificationId = uuid.uuid4().hex

    try:
        payload = readSignedPayload(extractScannedToken(scannedValue))
    except InvalidSignatureError:
        _recordVerification(
            verificationId,
            None,
            BadgeVerificationResult.failed.value,
            [REASON_INVALID_SIGNATURE],
            verifiedAt,
        )
        return _buildVerificationResponse(
            [REASON_INVALID_SIGNATURE],
            signatureValid=False,
            verificationId=verificationId,
            verifiedAt=verifiedAt,
        )
    except MalformedPayloadError:
        _recordVerification(
            verificationId,
            None,
            BadgeVerificationResult.failed.value,
            [REASON_MALFORMED_TOKEN],
            verifiedAt,
        )
        return _buildVerificationResponse(
            [REASON_MALFORMED_TOKEN],
            signatureValid=True,
            verificationId=verificationId,
            verifiedAt=verifiedAt,
        )
    except MalformedTokenError:
        _recordVerification(
            verificationId,
            None,
            BadgeVerificationResult.failed.value,
            [REASON_MALFORMED_TOKEN],
            verifiedAt,
        )
        return _buildVerificationResponse(
            [REASON_MALFORMED_TOKEN],
            signatureValid=False,
            verificationId=verificationId,
            verifiedAt=verifiedAt,
        )

    credentialVersion = payload.get("v")
    if (
        isinstance(credentialVersion, int)
        and not isinstance(credentialVersion, bool)
        and credentialVersion != CREDENTIAL_VERSION
    ):
        _recordVerification(
            verificationId,
            None,
            BadgeVerificationResult.failed.value,
            [REASON_UNSUPPORTED_VERSION],
            verifiedAt,
        )
        return _buildVerificationResponse(
            [REASON_UNSUPPORTED_VERSION],
            signatureValid=True,
            verificationId=verificationId,
            verifiedAt=verifiedAt,
        )

    try:
        credential = BadgeVerificationCredential.model_validate(payload)
    except ValidationError:
        _recordVerification(
            verificationId,
            None,
            BadgeVerificationResult.failed.value,
            [REASON_MALFORMED_TOKEN],
            verifiedAt,
        )
        return _buildVerificationResponse(
            [REASON_MALFORMED_TOKEN],
            signatureValid=True,
            verificationId=verificationId,
            verifiedAt=verifiedAt,
        )

    reasons: list[str] = []
    issuedAt = credential.iat.isoformat()
    expiresAt = credential.exp.isoformat()
    badgeStatus = None

    if verifiedAtDate < credential.iat:
        reasons.append(REASON_CREDENTIAL_NOT_YET_VALID)

    if verifiedAtDate >= credential.exp:
        reasons.append(REASON_EXPIRED)

    statusReasons, badgeStatus = _checkLiveBadgeStatus(
        credential.uid,
        credential.bid,
        verifiedAtDate,
    )
    reasons.extend(statusReasons)

    disclosedAttributes = {
        attribute.value: value for attribute, value in credential.att.items()
    }

    response = _buildVerificationResponse(
        reasons,
        signatureValid=True,
        verificationId=verificationId,
        verifiedAt=verifiedAt,
        disclosedAttributes=disclosedAttributes,
        badgeStatus=badgeStatus,
        issuedAt=issuedAt,
        expiresAt=expiresAt,
    )
    _recordVerification(
        verificationId,
        credential.uid,
        response["result"],
        reasons,
        verifiedAt,
    )

    return response
