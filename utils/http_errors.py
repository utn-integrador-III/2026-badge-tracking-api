from contextlib import contextmanager

from fastapi import HTTPException


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
