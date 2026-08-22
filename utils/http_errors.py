from contextlib import contextmanager

from fastapi import HTTPException, status
from pydantic import ValidationError


@contextmanager
def serviceErrorsAsHttp(errorStatuses: dict[type[Exception], int]):
    """Translate service exceptions into the HTTP status codes they map to."""
    try:
        yield
    except tuple(errorStatuses) as error:
        raise HTTPException(
            status_code=errorStatuses[type(error)],
            detail=str(error),
        ) from error


@contextmanager
def validationErrorsAsHttp():
    """Report a request model built by hand with the same 422 as the router.

    Multipart endpoints have to assemble their request model from individual
    form fields, so its validators run outside the automatic request parsing.
    """
    try:
        yield
    except ValidationError as error:
        firstError = error.errors(include_url=False)[0]
        field = firstError["loc"][0] if firstError["loc"] else "request"
        message = firstError["msg"].removeprefix("Value error, ")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field}: {message}",
        ) from error
