from typing import Any

from models.user import UserRole
from services.user_service import (
    assertValidInstitutionalId,
    authenticateBadgeHolder,
    findCurrentBadge,
)


class NotAnAdminError(Exception):
    pass


def authenticateAdmin(
    institutionalId: str,
    pin: str,
    forbiddenMessage: str = "Only an institutional admin can manage badges",
) -> dict[str, Any]:
    assertValidInstitutionalId(institutionalId)
    admin = authenticateBadgeHolder(institutionalId, pin)

    if admin["role"] != UserRole.admin.value:
        raise NotAnAdminError(forbiddenMessage)

    if not findCurrentBadge(admin["id"], {"id": 1}):
        raise NotAnAdminError(forbiddenMessage)

    return admin
