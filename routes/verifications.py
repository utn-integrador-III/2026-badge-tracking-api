from fastapi import APIRouter, HTTPException, status

from models.user import AgeProofVerificationResponse
from services.user_service import (
    AgeProofTokenExpiredError,
    AgeProofTokenNotFoundError,
    verifyAgeProof as verifyAgeProofService,
)


router = APIRouter(prefix="/verifications", tags=["Verifications"])


@router.get(
    "/age-proof/{token}",
    response_model=AgeProofVerificationResponse,
)
def verifyAgeProof(token: str) -> dict:
    try:
        return verifyAgeProofService(token)
    except AgeProofTokenNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except AgeProofTokenExpiredError as error:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=str(error),
        ) from error
