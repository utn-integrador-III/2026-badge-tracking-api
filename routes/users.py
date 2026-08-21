from fastapi import APIRouter, HTTPException, Response, status

from models.user import (
    AgeProofQrResponse,
    BadgeDeliveryPinRequest,
    BadgeDeliveryResponse,
    BadgeNotificationResponse,
    BadgeProfileResponse,
    BadgeRenewalRequestResponse,
    BadgeVerificationQrResponse,
    ExtendedBadgeProfileResponse,
    GenerateAgeProofQrRequest,
    GenerateBadgeVerificationQrRequest,
    PendingBadgeDeliveriesResponse,
    PendingBadgeNotificationsResponse,
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
from services.badge_notification_service import (
    BadgeNotificationNotFoundError,
    NoRenewableBadgeError,
    acknowledgeNotification as acknowledgeNotificationService,
    dismissNotification as dismissNotificationService,
    fetchPendingNotifications as fetchPendingNotificationsService,
    requestBadgeRenewal as requestBadgeRenewalService,
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
    getExtendedBadgeProfile as getExtendedBadgeProfileService,
    registerInstitutionalIdentity as registerInstitutionalIdentityService,
    setUserPin as setUserPinService,
    validateUserPin as validateUserPinService,
)
from utils.http_errors import serviceErrorsAsHttp


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


PROFILE_DETAILS_ERROR_STATUSES = {
    InvalidInstitutionalIdError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    UserNotFoundError: status.HTTP_404_NOT_FOUND,
    PinNotSetError: status.HTTP_409_CONFLICT,
    InvalidPinError: status.HTTP_401_UNAUTHORIZED,
    UserBadgeProfileNotFoundError: status.HTTP_404_NOT_FOUND,
}


@router.post(
    "/{institutionalId}/badge-profile/details",
    response_model=ExtendedBadgeProfileResponse,
    status_code=status.HTTP_200_OK,
)
def getExtendedBadgeProfile(
    institutionalId: str,
    request: ValidatePinRequest,
    response: Response,
) -> dict:
    with serviceErrorsAsHttp(PROFILE_DETAILS_ERROR_STATUSES):
        details = getExtendedBadgeProfileService(institutionalId, request.pin)

    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["Referrer-Policy"] = "no-referrer"
    return details


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


BADGE_DELIVERY_ERROR_STATUSES = {
    InvalidInstitutionalIdError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    UserNotFoundError: status.HTTP_404_NOT_FOUND,
    PinNotSetError: status.HTTP_409_CONFLICT,
    InvalidPinError: status.HTTP_401_UNAUTHORIZED,
    BadgeDeliveryNotFoundError: status.HTTP_404_NOT_FOUND,
}


BADGE_NOTIFICATION_ERROR_STATUSES = {
    InvalidInstitutionalIdError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    UserNotFoundError: status.HTTP_404_NOT_FOUND,
    PinNotSetError: status.HTTP_409_CONFLICT,
    InvalidPinError: status.HTTP_401_UNAUTHORIZED,
    BadgeNotificationNotFoundError: status.HTTP_404_NOT_FOUND,
    NoRenewableBadgeError: status.HTTP_409_CONFLICT,
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
) -> dict:
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


@router.post(
    "/{institutionalId}/badge-notifications/fetch",
    response_model=PendingBadgeNotificationsResponse,
    status_code=status.HTTP_200_OK,
)
def fetchPendingBadgeNotifications(
    institutionalId: str,
    request: BadgeDeliveryPinRequest,
) -> dict:
    with serviceErrorsAsHttp(BADGE_NOTIFICATION_ERROR_STATUSES):
        return fetchPendingNotificationsService(institutionalId, request.pin)


@router.post(
    "/{institutionalId}/badge-notifications/{notificationId}/acknowledge",
    response_model=BadgeNotificationResponse,
    status_code=status.HTTP_200_OK,
)
def acknowledgeBadgeNotification(
    institutionalId: str,
    notificationId: str,
    request: BadgeDeliveryPinRequest,
) -> dict:
    with serviceErrorsAsHttp(BADGE_NOTIFICATION_ERROR_STATUSES):
        return acknowledgeNotificationService(
            institutionalId,
            request.pin,
            notificationId,
        )


@router.post(
    "/{institutionalId}/badge-notifications/{notificationId}/dismiss",
    response_model=BadgeNotificationResponse,
    status_code=status.HTTP_200_OK,
)
def dismissBadgeNotification(
    institutionalId: str,
    notificationId: str,
    request: BadgeDeliveryPinRequest,
) -> dict:
    with serviceErrorsAsHttp(BADGE_NOTIFICATION_ERROR_STATUSES):
        return dismissNotificationService(
            institutionalId,
            request.pin,
            notificationId,
        )


@router.post(
    "/{institutionalId}/badge-renewals",
    response_model=BadgeRenewalRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
def requestBadgeRenewal(
    institutionalId: str,
    request: BadgeDeliveryPinRequest,
) -> dict:
    with serviceErrorsAsHttp(BADGE_NOTIFICATION_ERROR_STATUSES):
        return requestBadgeRenewalService(institutionalId, request.pin)
