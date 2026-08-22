"""Countdown arithmetic shared by everything that hands out a QR code."""

import math
from datetime import datetime, timedelta, timezone


def parseTimestamp(value: object) -> datetime | None:
    try:
        parsedValue = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None

    if parsedValue.tzinfo is None:
        return parsedValue.replace(tzinfo=timezone.utc)

    return parsedValue


def remainingSeconds(expiresAt: object, reference: datetime) -> int:
    """Return whole seconds left, rounded up so the last second still counts."""
    expiresAtDate = (
        expiresAt if isinstance(expiresAt, datetime) else parseTimestamp(expiresAt)
    )
    if not expiresAtDate:
        return 0

    remainingTime = expiresAtDate - reference
    if remainingTime <= timedelta(0):
        return 0

    return math.ceil(remainingTime / timedelta(seconds=1))


def elapsedLifetimeInSeconds(issuedAt: object, expiresAt: object) -> int:
    """Return the full lifetime a QR code was minted with."""
    issuedAtDate = parseTimestamp(issuedAt)
    expiresAtDate = parseTimestamp(expiresAt)

    if not issuedAtDate or not expiresAtDate:
        return 0

    return max(round((expiresAtDate - issuedAtDate) / timedelta(seconds=1)), 0)
