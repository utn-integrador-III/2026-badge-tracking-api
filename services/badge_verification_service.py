import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from database.connection import getDatabase
from models.user import (
    BadgeVerificationResult,
    DisclosableAttribute,
    GenerateBadgeVerificationQrRequest,
)
from services.user_service import (
    BadgeNotShareableError,
    SHAREABLE_BADGE_STATUSES,
    UserBadgeProfileNotFoundError,
    assertValidInstitutionalId,
    authenticateBadgeHolder,
    getVerificationBaseUrl,
)
from utils.qr_code import buildQrCodeDataUri
from utils.signing import (
    InvalidSignatureError,
    MalformedTokenError,
    readSignedPayload,
    signPayload,
)


BADGE_VERIFICATION_PATH = "/verifications/badge/"
CREDENTIAL_VERSION = 1

REASON_MALFORMED_TOKEN = "malformed_token"
REASON_INVALID_SIGNATURE = "invalid_signature"
REASON_UNSUPPORTED_VERSION = "unsupported_credential_version"
REASON_EXPIRED = "expired"
REASON_USER_NOT_FOUND = "user_not_found"
REASON_USER_INACTIVE = "user_inactive"
REASON_BADGE_NOT_FOUND = "badge_not_found"
REASON_BADGE_NOT_ACTIVE = "badge_not_active"


def _collectDisclosedAttributes(
    user: dict[str, Any],
    badge: dict[str, Any],
    disclose: list[DisclosableAttribute],
) -> dict[str, str | None]:
    availableAttributes: dict[DisclosableAttribute, str | None] = {
        DisclosableAttribute.fullName: user["full_name"],
        DisclosableAttribute.photoUrl: user.get("photo_url"),
        DisclosableAttribute.role: user["role"],
        DisclosableAttribute.institutionalId: user["institutional_id"],
        DisclosableAttribute.badgeCode: badge["badge_code"],
    }

    return {
        attribute.value: availableAttributes[attribute] for attribute in disclose
    }


def generateBadgeVerificationQr(
    institutionalId: str,
    request: GenerateBadgeVerificationQrRequest,
) -> dict:
    assertValidInstitutionalId(institutionalId)

    user = authenticateBadgeHolder(institutionalId, request.pin)

    database = getDatabase()
    badge = database.badges.find_one(
        {"user_id": user["id"]},
        {"badge_code": 1, "status": 1},
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

    disclosedAttributes = _collectDisclosedAttributes(user, badge, request.disclose)
    token = signPayload(
        {
            "v": CREDENTIAL_VERSION,
            "uid": user["id"],
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


def _checkLiveBadgeStatus(userId: Any) -> tuple[list[str], str | None]:
    database = getDatabase()
    user = database.users.find_one({"id": userId}, {"is_active": 1})

    if not user:
        return [REASON_USER_NOT_FOUND], None

    if not user["is_active"]:
        return [REASON_USER_INACTIVE], None

    badge = database.badges.find_one({"user_id": userId}, {"status": 1})

    if not badge:
        return [REASON_BADGE_NOT_FOUND], None

    if badge["status"] not in SHAREABLE_BADGE_STATUSES:
        return [REASON_BADGE_NOT_ACTIVE], badge["status"]

    return [], badge["status"]


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

    reasons: list[str] = []
    issuedAt = payload.get("iat")
    expiresAt = payload.get("exp")
    badgeStatus = None

    if payload.get("v") != CREDENTIAL_VERSION:
        reasons.append(REASON_UNSUPPORTED_VERSION)
    elif not isinstance(expiresAt, str):
        reasons.append(REASON_MALFORMED_TOKEN)
    else:
        if verifiedAtDate >= datetime.fromisoformat(expiresAt):
            reasons.append(REASON_EXPIRED)

        statusReasons, badgeStatus = _checkLiveBadgeStatus(payload.get("uid"))
        reasons.extend(statusReasons)

    response = _buildVerificationResponse(
        reasons,
        signatureValid=True,
        verificationId=verificationId,
        verifiedAt=verifiedAt,
        disclosedAttributes=payload.get("att", {}),
        badgeStatus=badgeStatus,
        issuedAt=issuedAt,
        expiresAt=expiresAt,
    )
    _recordVerification(
        verificationId,
        payload.get("uid"),
        response["result"],
        reasons,
        verifiedAt,
    )

    return response
