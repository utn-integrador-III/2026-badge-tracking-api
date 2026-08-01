from fastapi import APIRouter, status

from models.user import IssueBadgeRequest, IssueBadgeResponse
from services.badge_issuance_service import (
    BadgeHolderNotFoundError,
    NotAnAdminError,
    issueBadge as issueBadgeService,
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
