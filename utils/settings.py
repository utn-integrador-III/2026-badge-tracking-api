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
