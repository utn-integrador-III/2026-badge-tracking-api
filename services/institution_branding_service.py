import uuid
from datetime import datetime, timezone
from typing import Any

from pymongo import ReturnDocument

from database.connection import getDatabase
from models.user import UpdateInstitutionBrandingRequest
from utils.branding import (
    MAX_LOGO_SIZE_IN_BYTES,
    SUPPORTED_LOGO_CONTENT_TYPES,
    contrastTextColor,
    detectImageContentType,
)
from utils.settings import getIssuingAuthority, getVerificationBaseUrl


class InvalidLogoError(Exception):
    pass


class UnsupportedLogoFormatError(Exception):
    pass


class LogoTooLargeError(Exception):
    pass


class BrandingLogoNotFoundError(Exception):
    pass


# The palette a badge falls back to until its institution uploads a brand.
DEFAULT_PRIMARY_COLOR = "#1F3B73"
DEFAULT_SECONDARY_COLOR = "#C8A227"


def _buildLogoUrl(logoAssetId: str) -> str:
    return (
        f"{getVerificationBaseUrl()}/institutions/branding/logos/{logoAssetId}"
    )


def _toBrandingResponse(
    institution: str,
    branding: dict[str, Any] | None,
) -> dict:
    storedBranding = branding or {}
    primaryColor = storedBranding.get("primary_color") or DEFAULT_PRIMARY_COLOR
    secondaryColor = (
        storedBranding.get("secondary_color") or DEFAULT_SECONDARY_COLOR
    )
    logoAssetId = storedBranding.get("logo_asset_id")

    return {
        "institution": institution,
        "primaryColor": primaryColor,
        "secondaryColor": secondaryColor,
        "contrastTextColor": contrastTextColor(primaryColor),
        "logoUrl": _buildLogoUrl(logoAssetId) if logoAssetId else None,
        "logoContentType": storedBranding.get("logo_content_type"),
        "logoSizeInBytes": storedBranding.get("logo_size_in_bytes"),
        "logoUpdatedAt": storedBranding.get("logo_updated_at"),
        "isCustomized": bool(branding),
        "updatedAt": storedBranding.get("updated_at"),
    }


def getInstitutionBranding(institution: str | None = None) -> dict:
    """Return an institution's brand, falling back to the default palette."""
    institution = institution or getIssuingAuthority()
    branding = getDatabase().institution_branding.find_one(
        {"institution": institution}
    )

    return _toBrandingResponse(institution, branding)


def resolveBadgeBranding(badge: dict[str, Any]) -> dict:
    """Return the brand of the institution that issued a badge.

    A badge keeps the authority it was issued under, so a reissued badge always
    carries the brand of the institution that granted it.
    """
    return getInstitutionBranding(
        badge.get("issuing_authority") or getIssuingAuthority()
    )


def _buildLogoFields(logoContent: bytes, updatedAt: str) -> dict[str, Any]:
    if not logoContent:
        raise InvalidLogoError("The logo file is empty")

    if len(logoContent) > MAX_LOGO_SIZE_IN_BYTES:
        raise LogoTooLargeError(
            f"The logo must not exceed {MAX_LOGO_SIZE_IN_BYTES} bytes"
        )

    # The bytes decide the format. A client can declare any content type, and
    # this image is served back to every badge viewer.
    contentType = detectImageContentType(logoContent)
    if contentType not in SUPPORTED_LOGO_CONTENT_TYPES:
        raise UnsupportedLogoFormatError(
            "The logo must be one of "
            f"{', '.join(SUPPORTED_LOGO_CONTENT_TYPES)}"
        )

    return {
        # A fresh asset id per upload keeps cached logos from going stale.
        "logo_asset_id": uuid.uuid4().hex,
        "logo_content_type": contentType,
        "logo_bytes": logoContent,
        "logo_size_in_bytes": len(logoContent),
        "logo_updated_at": updatedAt,
    }


def updateInstitutionBranding(
    request: UpdateInstitutionBrandingRequest,
    logoContent: bytes | None = None,
) -> dict:
    # Imported here so the badge profile can read branding without the
    # authentication services importing this module back.
    from services.admin_service import authenticateAdmin
    from services.user_service import findCurrentBadge

    admin = authenticateAdmin(
        request.adminInstitutionalId,
        request.adminPin,
        "Only an institutional admin can manage badge branding",
    )
    adminBadge = findCurrentBadge(admin["id"], {"issuing_authority": 1})
    institution = (adminBadge or {}).get("issuing_authority") or (
        getIssuingAuthority()
    )

    updatedAt = datetime.now(timezone.utc).isoformat()
    updatedFields: dict[str, Any] = {
        "primary_color": request.primaryColor,
        "secondary_color": request.secondaryColor,
        "updated_at": updatedAt,
        "updated_by_user_id": admin["id"],
    }

    # Colours can be adjusted on their own; the logo stays until replaced.
    if logoContent is not None:
        updatedFields.update(_buildLogoFields(logoContent, updatedAt))

    branding = getDatabase().institution_branding.find_one_and_update(
        {"institution": institution},
        {
            "$set": updatedFields,
            "$setOnInsert": {"created_at": updatedAt},
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )

    return _toBrandingResponse(institution, branding)


def getBrandingLogo(logoAssetId: str) -> dict:
    branding = getDatabase().institution_branding.find_one(
        {"logo_asset_id": logoAssetId},
        {"logo_bytes": 1, "logo_content_type": 1},
    )

    if not branding or not branding.get("logo_bytes"):
        raise BrandingLogoNotFoundError("Institution logo was not found")

    return {
        "content": bytes(branding["logo_bytes"]),
        "contentType": branding["logo_content_type"],
    }
