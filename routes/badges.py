from fastapi import APIRouter, Path, status

from models.user import (
    AdminBadgeSearchRequest,
    AdminBadgeSearchResponse,
    IssueBadgeRequest,
    IssueBadgeResponse,
    UpdateBadgeStatusRequest,
    UpdateBadgeStatusResponse,
)
from services.admin_service import NotAnAdminError
from services.badge_issuance_service import (
    BadgeHolderNotFoundError,
    issueBadge as issueBadgeService,
)
from services.badge_management_service import (
    BadgeNotFoundError,
    InvalidBadgeStatusTransitionError,
    searchBadgeHolders as searchBadgeHoldersService,
    updateBadgeStatus as updateBadgeStatusService,
)
from services.user_service import (
    InvalidInstitutionalIdError,
    InvalidPinError,
    PinNotSetError,
    UserNotFoundError,
)
from utils.http_errors import serviceErrorsAsHttp


router = APIRouter(prefix="/badges", tags=["Badges"])


ISSUE_BADGE_ERROR_STATUSES = {
    InvalidInstitutionalIdError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    UserNotFoundError: status.HTTP_404_NOT_FOUND,
    PinNotSetError: status.HTTP_409_CONFLICT,
    InvalidPinError: status.HTTP_401_UNAUTHORIZED,
    NotAnAdminError: status.HTTP_403_FORBIDDEN,
    BadgeHolderNotFoundError: status.HTTP_404_NOT_FOUND,
}


@router.post(
    "",
    response_model=IssueBadgeResponse,
    status_code=status.HTTP_201_CREATED,
)
def issueBadge(request: IssueBadgeRequest) -> dict:
    with serviceErrorsAsHttp(ISSUE_BADGE_ERROR_STATUSES):
        return issueBadgeService(request)


MANAGE_BADGE_ERROR_STATUSES = {
    InvalidInstitutionalIdError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    UserNotFoundError: status.HTTP_404_NOT_FOUND,
    PinNotSetError: status.HTTP_409_CONFLICT,
    InvalidPinError: status.HTTP_401_UNAUTHORIZED,
    NotAnAdminError: status.HTTP_403_FORBIDDEN,
    BadgeNotFoundError: status.HTTP_404_NOT_FOUND,
    InvalidBadgeStatusTransitionError: status.HTTP_409_CONFLICT,
}


@router.post(
    "/search",
    response_model=AdminBadgeSearchResponse,
    status_code=status.HTTP_200_OK,
)
def searchBadgeHolders(request: AdminBadgeSearchRequest) -> dict:
    with serviceErrorsAsHttp(MANAGE_BADGE_ERROR_STATUSES):
        return searchBadgeHoldersService(request)


@router.patch(
    "/{badgeId}/status",
    response_model=UpdateBadgeStatusResponse,
    status_code=status.HTTP_200_OK,
)
def updateBadgeStatus(
    request: UpdateBadgeStatusRequest,
    badgeId: int = Path(gt=0),
) -> dict:
    with serviceErrorsAsHttp(MANAGE_BADGE_ERROR_STATUSES):
        return updateBadgeStatusService(badgeId, request)
