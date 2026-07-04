from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


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


class SetPinRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    pin: str = Field(min_length=4, max_length=4, pattern=r"^\d{4}$")
    pinConfirm: str = Field(min_length=4, max_length=4, pattern=r"^\d{4}$")


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
