from fastapi import APIRouter, HTTPException, status

from models.user import (
    AgeProofQrResponse,
    BadgeProfileResponse,
    GenerateAgeProofQrRequest,
    RegisterInstitutionalIdentityRequest,
    RegisterInstitutionalIdentityResponse,
    SetPinRequest,
    SetPinResponse,
    ValidatePinRequest,
    ValidatePinResponse,
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


@router.post(
    "/{institutionalId}/age-proof-qr",
    response_model=AgeProofQrResponse,
    status_code=status.HTTP_201_CREATED,
)
def generateAgeProofQr(
    institutionalId: str,
    request: GenerateAgeProofQrRequest,
) -> dict:
    try:
        return generateAgeProofQrService(institutionalId, request)
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
    except UserBadgeProfileNotFoundError as error:
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
    except BirthDateNotSetError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    except BadgeNotShareableError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
