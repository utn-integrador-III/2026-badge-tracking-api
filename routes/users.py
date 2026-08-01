from fastapi import APIRouter, HTTPException, status

from models.user import (
    AgeProofQrResponse,
    BadgeProfileResponse,
    BadgeVerificationQrResponse,
    GenerateAgeProofQrRequest,
    GenerateBadgeVerificationQrRequest,
    RegisterInstitutionalIdentityRequest,
    RegisterInstitutionalIdentityResponse,
    SetPinRequest,
    SetPinResponse,
    ValidatePinRequest,
    ValidatePinResponse,
)
from services.badge_verification_service import (
    generateBadgeVerificationQr as generateBadgeVerificationQrService,
)
from services.user_service import (
    BadgeNotShareableError,
    BirthDateNotSetError,
    DuplicateUserError,
    InvalidInstitutionalIdError,
    InvalidPinError,
    PinAlreadySetError,
    PinMismatchError,
    PinNotSetError,
    UserBadgeProfileNotFoundError,
    UserNotFoundError,
    generateAgeProofQr as generateAgeProofQrService,
    getDigitalBadgeProfile as getDigitalBadgeProfileService,
    registerInstitutionalIdentity as registerInstitutionalIdentityService,
    setUserPin as setUserPinService,
    validateUserPin as validateUserPinService,
)


router = APIRouter(prefix="/users", tags=["Users"])


@router.post(
    "/institutional-identities",
    response_model=RegisterInstitutionalIdentityResponse,
    status_code=status.HTTP_201_CREATED,
)
def registerInstitutionalIdentity(
    request: RegisterInstitutionalIdentityRequest,
) -> dict:
    try:
        return registerInstitutionalIdentityService(request)
    except DuplicateUserError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error


@router.get(
    "/{institutionalId}/badge-profile",
    response_model=BadgeProfileResponse,
)
def getDigitalBadgeProfile(institutionalId: str) -> dict:
    try:
        return getDigitalBadgeProfileService(institutionalId)
    except InvalidInstitutionalIdError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error
    except UserBadgeProfileNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    
@router.post(
    "/{institutionalId}/pin",
    response_model=SetPinResponse,
    status_code=status.HTTP_201_CREATED,
)
def setUserPin(institutionalId: str, request: SetPinRequest) -> dict:
    if request.pin != request.pinConfirm:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="PIN and PIN confirmation do not match",
        )
    try:
        return setUserPinService(institutionalId, request)
    except InvalidInstitutionalIdError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error
    except UserNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except PinAlreadySetError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    except PinMismatchError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error
 
@router.post(
    "/{institutionalId}/pin/validate",
    response_model=ValidatePinResponse,
    status_code=status.HTTP_200_OK,
)
def validateUserPin(institutionalId: str, request: ValidatePinRequest) -> dict:
    try:
        return validateUserPinService(institutionalId, request.pin)
    except InvalidInstitutionalIdError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error
    except UserNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except PinNotSetError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    except InvalidPinError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(error),
        ) from error


SHARE_QR_ERROR_STATUSES = {
    InvalidInstitutionalIdError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    UserNotFoundError: status.HTTP_404_NOT_FOUND,
    UserBadgeProfileNotFoundError: status.HTTP_404_NOT_FOUND,
    PinNotSetError: status.HTTP_409_CONFLICT,
    InvalidPinError: status.HTTP_401_UNAUTHORIZED,
    BirthDateNotSetError: status.HTTP_409_CONFLICT,
    BadgeNotShareableError: status.HTTP_409_CONFLICT,
}


def _shareQrOrFail(buildQr, institutionalId: str, request):
    try:
        return buildQr(institutionalId, request)
    except tuple(SHARE_QR_ERROR_STATUSES) as error:
        raise HTTPException(
            status_code=SHARE_QR_ERROR_STATUSES[type(error)],
            detail=str(error),
        ) from error


@router.post(
    "/{institutionalId}/age-proof-qr",
    response_model=AgeProofQrResponse,
    status_code=status.HTTP_201_CREATED,
)
def generateAgeProofQr(
    institutionalId: str,
    request: GenerateAgeProofQrRequest,
) -> dict:
    return _shareQrOrFail(generateAgeProofQrService, institutionalId, request)


@router.post(
    "/{institutionalId}/verification-qr",
    response_model=BadgeVerificationQrResponse,
    status_code=status.HTTP_201_CREATED,
)
def generateBadgeVerificationQr(
    institutionalId: str,
    request: GenerateBadgeVerificationQrRequest,
) -> dict:
    return _shareQrOrFail(
        generateBadgeVerificationQrService,
        institutionalId,
        request,
    )
