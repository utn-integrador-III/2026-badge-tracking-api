from fastapi import APIRouter, HTTPException, status

from models.user import (
    RegisterInstitutionalIdentityRequest,
    RegisterInstitutionalIdentityResponse,
)
from services.user_service import (
    DuplicateUserError,
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
