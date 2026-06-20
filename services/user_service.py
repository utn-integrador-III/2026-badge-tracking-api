import uuid
from contextlib import closing
from datetime import datetime, timezone

from database.connection import getConnection
from models.user import RegisterInstitutionalIdentityRequest


class DuplicateUserError(Exception):
    pass


def registerInstitutionalIdentity(
    request: RegisterInstitutionalIdentityRequest,
) -> dict:
    createdAt = datetime.now(timezone.utc).isoformat()
    badgeCode = f"BADGE-{request.institutionalId.upper()}-{uuid.uuid4().hex[:8].upper()}"

    with closing(getConnection()) as connection:
        existingUser = connection.execute(
            """
            SELECT email, institutional_id
            FROM users
            WHERE email = ? OR institutional_id = ?
            """,
            (request.email, request.institutionalId),
        ).fetchone()

        if existingUser:
            if existingUser["email"] == request.email:
                raise DuplicateUserError("Email is already registered")
            raise DuplicateUserError("Institutional ID is already registered")

        with connection:
            userCursor = connection.execute(
                """
                INSERT INTO users (
                    full_name,
                    email,
                    role,
                    institutional_id,
                    is_active,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    request.fullName,
                    request.email,
                    request.role.value,
                    request.institutionalId,
                    1,
                    createdAt,
                ),
            )
            userId = userCursor.lastrowid

            badgeCursor = connection.execute(
                """
                INSERT INTO badges (
                    user_id,
                    badge_code,
                    status,
                    issued_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (userId, badgeCode, "issued", createdAt),
            )
            badgeId = badgeCursor.lastrowid

    return {
        "message": "User registered successfully",
        "user": {
            "id": userId,
            "fullName": request.fullName,
            "email": request.email,
            "role": request.role.value,
            "institutionalId": request.institutionalId,
            "isActive": True,
            "createdAt": createdAt,
        },
        "badge": {
            "id": badgeId,
            "userId": userId,
            "badgeCode": badgeCode,
            "status": "issued",
            "issuedAt": createdAt,
        },
    }
