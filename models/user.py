from datetime import date, datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


MAX_REALISTIC_AGE_IN_YEARS = 120


class UserRole(str, Enum):
    student = "student"
    professor = "professor"
    staff = "staff"


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
    status: str
    validFrom: str
    validUntil: str

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