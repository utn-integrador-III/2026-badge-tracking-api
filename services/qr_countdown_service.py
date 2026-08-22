"""The live countdown both parties watch while a QR code is on screen.

Reading a countdown never verifies anything and never records an audit entry,
so a screen can poll it once a second without filling the verification log.
"""

from datetime import datetime, timezone

from database.connection import getDatabase
from models.user import QrTokenType
from services.badge_verification_service import (
    BADGE_VERIFICATION_PATH,
    CREDENTIAL_VERSION,
)
from services.user_service import AGE_PROOF_VERIFICATION_PATH, hashAgeProofToken
from utils.countdown import elapsedLifetimeInSeconds, remainingSeconds
from utils.signing import (
    InvalidSignatureError,
    MalformedTokenError,
    readSignedPayload,
)


class QrTokenNotFoundError(Exception):
    pass


def extractCountdownToken(scannedValue: str) -> str:
    """Accept either a bare token or the URL the QR code encodes."""
    cleanedValue = scannedValue.strip()

    for verificationPath in (BADGE_VERIFICATION_PATH, AGE_PROOF_VERIFICATION_PATH):
        markerIndex = cleanedValue.rfind(verificationPath)
        if markerIndex != -1:
            cleanedValue = cleanedValue[markerIndex + len(verificationPath) :]
            break

    return cleanedValue.split("?")[0].split("#")[0]


def _buildCountdown(
    tokenType: QrTokenType,
    issuedAt: str,
    expiresAt: str,
    reference: datetime,
) -> dict:
    secondsLeft = remainingSeconds(expiresAt, reference)

    return {
        "tokenType": tokenType.value,
        "issuedAt": issuedAt,
        "expiresAt": expiresAt,
        # Lets a client correct for a device clock that drifted.
        "serverTime": reference.isoformat(),
        "totalSeconds": elapsedLifetimeInSeconds(issuedAt, expiresAt),
        "remainingSeconds": secondsLeft,
        "expired": secondsLeft == 0,
    }


def _readBadgeVerificationCountdown(
    token: str,
    reference: datetime,
) -> dict | None:
    try:
        payload = readSignedPayload(token)
    except (InvalidSignatureError, MalformedTokenError):
        return None

    issuedAt = payload.get("iat")
    expiresAt = payload.get("exp")
    if payload.get("v") != CREDENTIAL_VERSION:
        return None

    if not isinstance(issuedAt, str) or not isinstance(expiresAt, str):
        return None

    return _buildCountdown(
        QrTokenType.badgeVerification,
        issuedAt,
        expiresAt,
        reference,
    )


def _readAgeProofCountdown(token: str, reference: datetime) -> dict | None:
    ageProof = getDatabase().age_proof_tokens.find_one(
        {"token_hash": hashAgeProofToken(token)},
        {"issued_at": 1, "expires_at": 1},
    )

    if not ageProof:
        return None

    return _buildCountdown(
        QrTokenType.ageProof,
        ageProof["issued_at"],
        ageProof["expires_at"],
        reference,
    )


def getQrCountdown(scannedValue: str) -> dict:
    """Return how long a scanned QR code stays inside its time window.

    The countdown answers how much of the sharing window is left, not whether
    the credential behind it still holds up. Scanning it remains the
    authoritative check.
    """
    token = extractCountdownToken(scannedValue)
    reference = datetime.now(timezone.utc)

    countdown = _readBadgeVerificationCountdown(
        token,
        reference,
    ) or _readAgeProofCountdown(token, reference)

    if not countdown:
        # An unreadable token and an unknown one answer the same way, so a
        # forged token learns nothing from the difference.
        raise QrTokenNotFoundError("QR code was not found")

    return countdown
