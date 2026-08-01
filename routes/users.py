from fastapi import APIRouter, HTTPException, Response, status

from models.user import (
    AgeProofQrResponse,
    BadgeDeliveryPinRequest,
    BadgeDeliveryResponse,
    BadgeProfileResponse,
    BadgeVerificationQrResponse,
    GenerateAgeProofQrRequest,
    GenerateBadgeVerificationQrRequest,
    PendingBadgeDeliveriesResponse,
    RegisterInstitutionalIdentityRequest,
    RegisterInstitutionalIdentityResponse,
    SetPinRequest,
    SetPinResponse,
    ValidatePinRequest,
    ValidatePinResponse,
)
from services.badge_delivery_service import BadgeDeliveryNotFoundError
from services.badge_issuance_service import (
    acknowledgeBadgeDelivery as acknowledgeBadgeDeliveryService,
    fetchPendingBadgeDeliveries as fetchPendingBadgeDeliveriesService,
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
from utils.http_errors import serviceErrorsAsHttp
from utils.signing import SigningConfigurationError


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
    SigningConfigurationError: status.HTTP_503_SERVICE_UNAVAILABLE,
}


BADGE_DELIVERY_ERROR_STATUSES = {
    InvalidInstitutionalIdError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    UserNotFoundError: status.HTTP_404_NOT_FOUND,
    PinNotSetError: status.HTTP_409_CONFLICT,
    InvalidPinError: status.HTTP_401_UNAUTHORIZED,
    BadgeDeliveryNotFoundError: status.HTTP_404_NOT_FOUND,
}


@router.post(
    "/{institutionalId}/age-proof-qr",
    response_model=AgeProofQrResponse,
    status_code=status.HTTP_201_CREATED,
)
def generateAgeProofQr(
    institutionalId: str,
    request: GenerateAgeProofQrRequest,
) -> dict:
    with serviceErrorsAsHttp(SHARE_QR_ERROR_STATUSES):
        return generateAgeProofQrService(institutionalId, request)


@router.post(
    "/{institutionalId}/verification-qr",
    response_model=BadgeVerificationQrResponse,
    status_code=status.HTTP_201_CREATED,
)
def generateBadgeVerificationQr(
    institutionalId: str,
    request: GenerateBadgeVerificationQrRequest,
    response: Response,
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    with serviceErrorsAsHttp(SHARE_QR_ERROR_STATUSES):
        return generateBadgeVerificationQrService(institutionalId, request)


@router.post(
    "/{institutionalId}/badge-deliveries/fetch",
    response_model=PendingBadgeDeliveriesResponse,
    status_code=status.HTTP_200_OK,
)
def fetchPendingBadgeDeliveries(
    institutionalId: str,
    request: BadgeDeliveryPinRequest,
) -> dict:
    with serviceErrorsAsHttp(BADGE_DELIVERY_ERROR_STATUSES):
        return fetchPendingBadgeDeliveriesService(institutionalId, request.pin)


@router.post(
    "/{institutionalId}/badge-deliveries/{deliveryId}/acknowledge",
    response_model=BadgeDeliveryResponse,
    status_code=status.HTTP_200_OK,
)
def acknowledgeBadgeDelivery(
    institutionalId: str,
    deliveryId: str,
    request: BadgeDeliveryPinRequest,
) -> dict:
    with serviceErrorsAsHttp(BADGE_DELIVERY_ERROR_STATUSES):
        return acknowledgeBadgeDeliveryService(
            institutionalId,
            deliveryId,
            request.pin,
        )
