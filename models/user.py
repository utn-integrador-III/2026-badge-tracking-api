from datetime import date, datetime, timezone
from enum import Enum
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator


MAX_REALISTIC_AGE_IN_YEARS = 120


class UserRole(str, Enum):
    student = "student"
    professor = "professor"
    staff = "staff"
    admin = "admin"


DEFAULT_BADGE_VALIDITY_IN_DAYS = 365


class RegisterInstitutionalIdentityRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    fullName: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=150)
    role: UserRole
    institutionalId: str = Field(min_length=9, max_length=9, pattern=r"^\d{9}$")
    photoUrl: str | None = Field(default=None, max_length=255)
    birthDate: str | None = Field(
        default=None,
        description="Date of birth in YYYY-MM-DD format. Required to share age proof.",
    )
    nationality: str | None = Field(default=None, min_length=2, max_length=100)
    birthplace: str | None = Field(default=None, min_length=2, max_length=150)
    documentExpiry: str | None = Field(
        default=None,
        description="Physical identity document expiry date in YYYY-MM-DD format.",
    )
    digitalSignatureUrl: str | None = Field(
        default=None,
        max_length=2048,
        description="HTTPS URL of the holder's enrolled visual signature.",
    )

    @field_validator("fullName", "email", "institutionalId")
    @classmethod
    def trimRequiredText(cls, value: str) -> str:
        cleanedValue = value.strip()
        if not cleanedValue:
            raise ValueError("This field is required")
        return cleanedValue

    @field_validator("email")
    @classmethod
    def validateEmail(cls, value: str) -> str:
        normalizedEmail = value.lower()
        localPart, separator, domain = normalizedEmail.partition("@")

        if not separator or not localPart or "." not in domain:
            raise ValueError("Invalid email format")

        return normalizedEmail

    @field_validator("photoUrl")
    @classmethod
    def trimOptionalText(cls, value: str | None) -> str | None:
        if value is None:
            return None

        cleanedValue = value.strip()
        return cleanedValue or None

    @field_validator("nationality", "birthplace", mode="before")
    @classmethod
    def trimExtendedIdentityText(cls, value: object) -> object:
        if not isinstance(value, str):
            return value

        cleanedValue = value.strip()
        return cleanedValue or None

    @field_validator("birthDate")
    @classmethod
    def validateBirthDate(cls, value: str | None) -> str | None:
        if value is None:
            return None

        cleanedValue = value.strip()
        if not cleanedValue:
            return None

        try:
            birthDate = date.fromisoformat(cleanedValue)
        except ValueError as error:
            raise ValueError("Birth date must use the YYYY-MM-DD format") from error

        today = datetime.now(timezone.utc).date()
        if birthDate >= today:
            raise ValueError("Birth date must be in the past")

        if birthDate < date(today.year - MAX_REALISTIC_AGE_IN_YEARS, 1, 1):
            raise ValueError("Birth date is not realistic")

        return birthDate.isoformat()

    @field_validator("documentExpiry")
    @classmethod
    def validateDocumentExpiry(cls, value: str | None) -> str | None:
        if value is None:
            return None

        cleanedValue = value.strip()
        if not cleanedValue:
            return None

        try:
            documentExpiry = date.fromisoformat(cleanedValue)
        except ValueError as error:
            raise ValueError(
                "Document expiry must use the YYYY-MM-DD format"
            ) from error

        return documentExpiry.isoformat()

    @field_validator("digitalSignatureUrl", mode="before")
    @classmethod
    def validateDigitalSignatureUrl(cls, value: object) -> object:
        if not isinstance(value, str):
            return value

        cleanedValue = value.strip()
        if not cleanedValue:
            return None

        if any(character.isspace() for character in cleanedValue):
            raise ValueError("Digital signature URL must not contain whitespace")

        parsedUrl = urlsplit(cleanedValue)
        if parsedUrl.scheme.lower() != "https" or not parsedUrl.hostname:
            raise ValueError("Digital signature URL must use HTTPS")

        if parsedUrl.username is not None or parsedUrl.password is not None:
            raise ValueError("Digital signature URL must not include credentials")

        return cleanedValue


class UserResponse(BaseModel):
    id: int
    fullName: str
    email: str
    role: UserRole
    institutionalId: str
    photoUrl: str | None
    isActive: bool
    createdAt: str


class BadgeResponse(BaseModel):
    id: int
    userId: int
    badgeCode: str
    roleType: UserRole
    status: str
    issuedAt: str
    validFrom: str
    validUntil: str


class RegisterInstitutionalIdentityResponse(BaseModel):
    message: str
    user: UserResponse
    badge: BadgeResponse


class BadgeProfileResponse(BaseModel):
    photoUrl: str | None
    fullName: str
    role: UserRole
    institutionalId: str
    badgeCode: str
    roleType: UserRole
    status: str
    validFrom: str
    validUntil: str


class ExtendedBadgeProfileResponse(BadgeProfileResponse):
    issuedAt: str
    issuingAuthority: str
    nationality: str | None
    birthplace: str | None
    documentExpiry: str | None
    digitalSignatureUrl: str | None


class SetPinRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
 
    pin: str = Field(
        min_length=6,
        max_length=6,
        description="Numeric PIN of 6 to 6 digits",
    )
    pinConfirm: str = Field(
        min_length=6,
        max_length=6,
        description="Must match pin exactly",
    )
 
    @field_validator("pin")
    @classmethod
    def validatePin(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("PIN must contain digits only")
 
        if len(set(value)) == 1:
            raise ValueError("PIN cannot use the same digit repeated")
 
        sequential = "0123456789"
        if value in sequential or value in sequential[::-1]:
            raise ValueError("PIN cannot be a sequential number")
 
        return value
 
    @field_validator("pinConfirm", mode="after")
    @classmethod
    def trimPinConfirm(cls, value: str) -> str:
        return value
 
    def assertPinsMatch(self) -> None:
        if self.pin != self.pinConfirm:
            raise ValueError("PIN and PIN confirmation do not match")
 
 
class SetPinResponse(BaseModel):
    message: str
    institutionalId: str
    pinSetAt: str
 
 
class ValidatePinRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
 
    pin: str = Field(
        min_length=6,
        max_length=6,
        description="PIN to verify",
    )
 
    @field_validator("pin")
    @classmethod
    def validatePinFormat(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("PIN must contain digits only")
        return value
 
 
class ValidatePinResponse(BaseModel):
    valid: bool
    institutionalId: str
    message: str


class GenerateAgeProofQrRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    pin: str = Field(
        min_length=6,
        max_length=6,
        description="Badge holder PIN, required to authorize the share",
    )
    minimumAge: int = Field(
        default=18,
        ge=1,
        le=MAX_REALISTIC_AGE_IN_YEARS,
        description="Age threshold the verifying party needs to confirm",
    )
    expiresInSeconds: int = Field(
        default=120,
        ge=30,
        le=900,
        description="Lifetime of the QR code, between 30 and 900 seconds",
    )

    @field_validator("pin")
    @classmethod
    def validatePinFormat(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("PIN must contain digits only")
        return value


class AgeProofQrResponse(BaseModel):
    token: str
    verificationUrl: str
    qrCodeImage: str
    minimumAge: int
    meetsMinimumAge: bool
    issuedAt: str
    expiresAt: str
    expiresInSeconds: int


class AgeProofVerificationResponse(BaseModel):
    valid: bool
    minimumAge: int
    meetsMinimumAge: bool
    role: UserRole
    badgeStatus: str
    issuedAt: str
    expiresAt: str
    verifiedAt: str


class DisclosableAttribute(str, Enum):
    fullName = "fullName"
    photoUrl = "photoUrl"
    role = "role"
    institutionalId = "institutionalId"
    badgeCode = "badgeCode"


DEFAULT_DISCLOSED_ATTRIBUTES = [
    DisclosableAttribute.fullName,
    DisclosableAttribute.photoUrl,
    DisclosableAttribute.role,
]


class BadgeVerificationResult(str, Enum):
    passed = "pass"
    failed = "fail"


class GenerateBadgeVerificationQrRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    pin: str = Field(
        min_length=6,
        max_length=6,
        description="Badge holder PIN, required to authorize the share",
    )
    disclose: list[DisclosableAttribute] = Field(
        default=list(DEFAULT_DISCLOSED_ATTRIBUTES),
        min_length=1,
        max_length=len(DisclosableAttribute),
        description="Attributes the verifier is allowed to see",
    )
    expiresInSeconds: int = Field(
        default=120,
        ge=30,
        le=900,
        description="Lifetime of the QR code, between 30 and 900 seconds",
    )

    @field_validator("pin")
    @classmethod
    def validatePinFormat(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("PIN must contain digits only")
        return value

    @field_validator("disclose")
    @classmethod
    def rejectDuplicateAttributes(
        cls,
        value: list[DisclosableAttribute],
    ) -> list[DisclosableAttribute]:
        if len(set(value)) != len(value):
            raise ValueError("Disclosed attributes cannot be repeated")
        return value


class BadgeVerificationQrResponse(BaseModel):
    token: str
    verificationUrl: str
    qrCodeImage: str
    disclosedAttributes: list[DisclosableAttribute]
    issuedAt: str
    expiresAt: str
    expiresInSeconds: int


class ScanBadgeVerificationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    scannedValue: str = Field(
        min_length=1,
        max_length=4096,
        description="Raw QR content, either the verification URL or the bare token",
    )


class BadgeVerificationResponse(BaseModel):
    result: BadgeVerificationResult
    signatureValid: bool
    reasons: list[str]
    disclosedAttributes: dict[str, str | None]
    badgeStatus: str | None
    issuedAt: str | None
    expiresAt: str | None
    verifiedAt: str
    verificationId: str


class BadgeDeliveryStatus(str, Enum):
    pending = "pending"
    delivered = "delivered"
    superseded = "superseded"
    cancelled = "cancelled"


class BadgeLifecycleStatus(str, Enum):
    suspended = "suspended"
    revoked = "revoked"


class BadgeNotificationType(str, Enum):
    badgeExpiring = "badge_expiring"


class BadgeNotificationStatus(str, Enum):
    pending = "pending"
    delivered = "delivered"
    dismissed = "dismissed"
    resolved = "resolved"


class BadgeRenewalRequestStatus(str, Enum):
    requested = "requested"
    fulfilled = "fulfilled"
    cancelled = "cancelled"


class IssueBadgeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    adminInstitutionalId: str = Field(
        min_length=9,
        max_length=9,
        pattern=r"^\d{9}$",
        description="Institutional ID of the admin performing the issuance",
    )
    adminPin: str = Field(
        min_length=6,
        max_length=6,
        description="PIN of the admin performing the issuance",
    )
    institutionalId: str = Field(
        min_length=9,
        max_length=9,
        pattern=r"^\d{9}$",
        description="Institutional ID of the badge holder",
    )
    roleType: UserRole | None = Field(
        default=None,
        description="Badge role type. Defaults to the holder's institutional role.",
    )
    validForDays: int = Field(
        default=DEFAULT_BADGE_VALIDITY_IN_DAYS,
        ge=1,
        le=1825,
        description="How long the badge stays valid, between 1 and 1825 days",
    )

    @field_validator("adminPin")
    @classmethod
    def validateAdminPinFormat(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("PIN must contain digits only")
        return value


class AdminBadgeSearchRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    adminInstitutionalId: str = Field(
        min_length=9,
        max_length=9,
        pattern=r"^\d{9}$",
        description="Institutional ID of the admin performing the search",
    )
    adminPin: str = Field(
        min_length=6,
        max_length=6,
        description="PIN of the admin performing the search",
    )
    query: str = Field(
        min_length=2,
        max_length=150,
        description="Institutional ID, full name, or email to search for",
    )
    limit: int = Field(default=20, ge=1, le=50)

    @field_validator("adminPin")
    @classmethod
    def validateAdminPinFormat(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("PIN must contain digits only")
        return value

    @field_validator("query", mode="before")
    @classmethod
    def trimQuery(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class UpdateBadgeStatusRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    adminInstitutionalId: str = Field(
        min_length=9,
        max_length=9,
        pattern=r"^\d{9}$",
        description="Institutional ID of the admin changing the badge status",
    )
    adminPin: str = Field(
        min_length=6,
        max_length=6,
        description="PIN of the admin changing the badge status",
    )
    status: BadgeLifecycleStatus
    reason: str = Field(
        min_length=3,
        max_length=250,
        description="Reason for suspending or revoking the badge",
    )

    @field_validator("adminPin")
    @classmethod
    def validateAdminPinFormat(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("PIN must contain digits only")
        return value

    @field_validator("reason", mode="before")
    @classmethod
    def trimReason(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class AdminBadgeSearchResult(BaseModel):
    userId: int
    fullName: str
    email: str
    institutionalId: str
    role: UserRole
    isActive: bool
    badge: BadgeResponse | None


class AdminBadgeSearchResponse(BaseModel):
    count: int
    results: list[AdminBadgeSearchResult]


class UpdateBadgeStatusResponse(BaseModel):
    message: str
    badge: BadgeResponse
    previousStatus: str
    changed: bool
    changedAt: str
    reason: str


class BadgeDeliveryResponse(BaseModel):
    deliveryId: str
    badgeId: int
    badgeCode: str
    roleType: UserRole
    status: BadgeDeliveryStatus
    validFrom: str
    validUntil: str
    triggeredAt: str
    deliveredAt: str | None


class IssueBadgeResponse(BaseModel):
    message: str
    badge: BadgeResponse
    supersededBadgeId: int | None
    delivery: BadgeDeliveryResponse


class PendingBadgeDeliveriesResponse(BaseModel):
    institutionalId: str
    deliveries: list[BadgeDeliveryResponse]


class BadgeDeliveryPinRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    pin: str = Field(
        min_length=6,
        max_length=6,
        description="Badge holder PIN, proving the request comes from their device",
    )

    @field_validator("pin")
    @classmethod
    def validatePinFormat(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("PIN must contain digits only")
        return value


class BadgeNotificationResponse(BaseModel):
    notificationId: str
    type: BadgeNotificationType
    status: BadgeNotificationStatus
    badgeId: int
    badgeCode: str
    title: str
    body: str
    actionLabel: str
    actionUrl: str
    daysUntilExpiry: int
    expired: bool
    validUntil: str
    createdAt: str
    deliveredAt: str | None


class PendingBadgeNotificationsResponse(BaseModel):
    institutionalId: str
    notifications: list[BadgeNotificationResponse]


class BadgeRenewalRequestResponse(BaseModel):
    requestId: str
    badgeId: int
    badgeCode: str
    status: BadgeRenewalRequestStatus
    validUntil: str
    daysUntilExpiry: int
    requestedAt: str
    fulfilledAt: str | None
    fulfilledBadgeId: int | None
