import base64
import hashlib
import hmac
import json
import os


MINIMUM_SIGNING_KEY_BYTES = 32
FORBIDDEN_SIGNING_KEYS = frozenset(
    {
        "development-only-badge-signing-key",
        "replace-with-a-random-secret-of-at-least-32-bytes",
    }
)


class MalformedTokenError(Exception):
    pass


class MalformedPayloadError(MalformedTokenError):
    """Raised after a valid signature is found over an unreadable payload."""


class InvalidSignatureError(Exception):
    pass


class SigningConfigurationError(RuntimeError):
    pass


def getSigningKey() -> bytes:
    configuredKey = os.getenv("BADGE_TRACKING_SIGNING_KEY")
    if not configuredKey or not configuredKey.strip():
        raise SigningConfigurationError(
            "BADGE_TRACKING_SIGNING_KEY must be configured"
        )

    if configuredKey != configuredKey.strip():
        raise SigningConfigurationError(
            "BADGE_TRACKING_SIGNING_KEY cannot have surrounding whitespace"
        )

    if configuredKey in FORBIDDEN_SIGNING_KEYS:
        raise SigningConfigurationError(
            "BADGE_TRACKING_SIGNING_KEY cannot use a known placeholder"
        )

    signingKey = configuredKey.encode()
    if len(signingKey) < MINIMUM_SIGNING_KEY_BYTES:
        raise SigningConfigurationError(
            "BADGE_TRACKING_SIGNING_KEY must contain at least 32 bytes"
        )

    return signingKey


def _encodeSegment(rawBytes: bytes) -> str:
    return base64.urlsafe_b64encode(rawBytes).decode().rstrip("=")


def _decodeSegment(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def _buildSignature(payloadSegment: str) -> str:
    signature = hmac.new(
        getSigningKey(),
        payloadSegment.encode(),
        hashlib.sha256,
    ).digest()
    return _encodeSegment(signature)


def signPayload(payload: dict) -> str:
    serializedPayload = json.dumps(
        payload,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    payloadSegment = _encodeSegment(serializedPayload)

    return f"{payloadSegment}.{_buildSignature(payloadSegment)}"


def readSignedPayload(token: str) -> dict:
    payloadSegment, separator, signatureSegment = token.partition(".")

    if not separator or not payloadSegment or not signatureSegment:
        raise MalformedTokenError("Token is malformed")

    if not hmac.compare_digest(_buildSignature(payloadSegment), signatureSegment):
        raise InvalidSignatureError("Token signature is not valid")

    try:
        payload = json.loads(_decodeSegment(payloadSegment))
    except (UnicodeError, ValueError) as error:
        raise MalformedPayloadError("Token payload could not be read") from error

    if not isinstance(payload, dict):
        raise MalformedPayloadError("Token payload must be a JSON object")

    return payload
