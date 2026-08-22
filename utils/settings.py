"""Deployment-wide settings the institution configures through the environment."""

import os


DEFAULT_ISSUING_AUTHORITY = "Universidad Técnica Nacional"
DEFAULT_VERIFICATION_BASE_URL = "http://127.0.0.1:8000"


def getIssuingAuthority() -> str:
    configuredAuthority = os.getenv(
        "BADGE_TRACKING_ISSUING_AUTHORITY",
        DEFAULT_ISSUING_AUTHORITY,
    ).strip()
    return configuredAuthority or DEFAULT_ISSUING_AUTHORITY


def getVerificationBaseUrl() -> str:
    baseUrl = os.getenv(
        "BADGE_TRACKING_VERIFICATION_BASE_URL",
        DEFAULT_VERIFICATION_BASE_URL,
    )
    return baseUrl.rstrip("/")


# A shared QR code cannot be left lying around, so it is short lived by
# default. The bounds apply to the configured default and to what a client may
# ask for, so neither can produce a code that is unusable or long lived.
DEFAULT_QR_LIFETIME_IN_SECONDS = 60
MIN_QR_LIFETIME_IN_SECONDS = 30
MAX_QR_LIFETIME_IN_SECONDS = 900


def getQrLifetimeInSeconds() -> int:
    """Return the lifetime a QR code gets when the client does not choose one."""
    configuredLifetime = os.getenv(
        "BADGE_TRACKING_QR_LIFETIME_SECONDS",
        "",
    ).strip()
    if not configuredLifetime:
        return DEFAULT_QR_LIFETIME_IN_SECONDS

    try:
        lifetimeInSeconds = int(configuredLifetime)
    except ValueError:
        return DEFAULT_QR_LIFETIME_IN_SECONDS

    if not (
        MIN_QR_LIFETIME_IN_SECONDS
        <= lifetimeInSeconds
        <= MAX_QR_LIFETIME_IN_SECONDS
    ):
        return DEFAULT_QR_LIFETIME_IN_SECONDS

    return lifetimeInSeconds
