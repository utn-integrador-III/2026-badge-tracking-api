import base64
import hashlib
import hmac
import json
import os


DEVELOPMENT_ONLY_SIGNING_KEY = "development-only-badge-signing-key"


class MalformedTokenError(Exception):
    pass


class InvalidSignatureError(Exception):
    pass


def getSigningKey() -> bytes:
    return os.getenv(
        "BADGE_TRACKING_SIGNING_KEY",
        DEVELOPMENT_ONLY_SIGNING_KEY,
    ).encode()


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
        return json.loads(_decodeSegment(payloadSegment))
    except ValueError as error:
        raise MalformedTokenError("Token payload could not be read") from error
