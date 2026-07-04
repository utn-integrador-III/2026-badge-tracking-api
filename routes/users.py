from fastapi import APIRouter, HTTPException, status

from models.user import (
    BadgeProfileResponse,
    RegisterInstitutionalIdentityRequest,
    RegisterInstitutionalIdentityResponse,
)
from services.user_service import (
    DuplicateUserError,
    InvalidInstitutionalIdError,
    UserBadgeProfileNotFoundError,
    getDigitalBadgeProfile as getDigitalBadgeProfileService,
    registerInstitutionalIdentity as registerInstitutionalIdentityService,
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
