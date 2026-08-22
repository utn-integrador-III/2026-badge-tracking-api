from typing import Annotated

from fastapi import APIRouter, File, Form, Response, UploadFile, status

from models.user import (
    InstitutionBrandingResponse,
    UpdateInstitutionBrandingRequest,
)
from services.admin_service import NotAnAdminError
from services.institution_branding_service import (
    BrandingLogoNotFoundError,
    InvalidLogoError,
    LogoTooLargeError,
    UnsupportedLogoFormatError,
    getBrandingLogo as getBrandingLogoService,
    getInstitutionBranding as getInstitutionBrandingService,
    updateInstitutionBranding as updateInstitutionBrandingService,
)
from services.user_service import (
    InvalidInstitutionalIdError,
    InvalidPinError,
    PinNotSetError,
    UserNotFoundError,
)
from utils.branding import MAX_LOGO_SIZE_IN_BYTES
from utils.http_errors import serviceErrorsAsHttp, validationErrorsAsHttp


router = APIRouter(prefix="/institutions", tags=["Institutions"])


BRANDING_ERROR_STATUSES = {
    InvalidInstitutionalIdError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    UserNotFoundError: status.HTTP_404_NOT_FOUND,
    PinNotSetError: status.HTTP_409_CONFLICT,
    InvalidPinError: status.HTTP_401_UNAUTHORIZED,
    NotAnAdminError: status.HTTP_403_FORBIDDEN,
    InvalidLogoError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    UnsupportedLogoFormatError: status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    LogoTooLargeError: status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
    BrandingLogoNotFoundError: status.HTTP_404_NOT_FOUND,
}


@router.get(
    "/branding",
    response_model=InstitutionBrandingResponse,
    status_code=status.HTTP_200_OK,
)
def getInstitutionBranding() -> dict:
    return getInstitutionBrandingService()


@router.put(
    "/branding",
    response_model=InstitutionBrandingResponse,
    status_code=status.HTTP_200_OK,
)
def updateInstitutionBranding(
    adminInstitutionalId: Annotated[str, Form()],
    adminPin: Annotated[str, Form()],
    primaryColor: Annotated[str, Form()],
    secondaryColor: Annotated[str, Form()],
    logo: Annotated[UploadFile | None, File()] = None,
) -> dict:
    # FastAPI nests a form model when the endpoint also takes a file, so the
    # fields arrive separately and the model is built from them here.
    with validationErrorsAsHttp():
        request = UpdateInstitutionBrandingRequest(
            adminInstitutionalId=adminInstitutionalId,
            adminPin=adminPin,
            primaryColor=primaryColor,
            secondaryColor=secondaryColor,
        )

    logoContent = None
    # A form without a chosen file still sends an empty part, which means the
    # admin is only adjusting colours.
    if logo is not None and logo.filename:
        # One byte over the limit is enough to reject it, so an oversized
        # upload is never held in memory in full.
        logoContent = logo.file.read(MAX_LOGO_SIZE_IN_BYTES + 1)

    with serviceErrorsAsHttp(BRANDING_ERROR_STATUSES):
        return updateInstitutionBrandingService(request, logoContent)


@router.get(
    "/branding/logos/{logoAssetId}",
    response_class=Response,
    status_code=status.HTTP_200_OK,
)
def getInstitutionBrandingLogo(logoAssetId: str) -> Response:
    with serviceErrorsAsHttp(BRANDING_ERROR_STATUSES):
        logo = getBrandingLogoService(logoAssetId)

    return Response(
        content=logo["content"],
        media_type=logo["contentType"],
        headers={
            # A new upload gets a new asset id, so this one never changes.
            "Cache-Control": "public, max-age=31536000, immutable",
            "Content-Disposition": "inline",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "X-Content-Type-Options": "nosniff",
        },
    )
