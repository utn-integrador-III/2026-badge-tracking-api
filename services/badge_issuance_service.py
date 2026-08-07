import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from database.connection import getDatabase
from models.user import IssueBadgeRequest, UserRole
from services.badge_delivery_service import (
    acknowledgeDelivery,
    listPendingDeliveries,
    supersedePendingDeliveries,
    triggerBadgeDelivery,
)
from services.user_service import (
    assertValidInstitutionalId,
    authenticateBadgeHolder,
    findCurrentBadge,
    getNextSequence,
    getIssuingAuthority,
)


class NotAnAdminError(Exception):
    pass


class BadgeHolderNotFoundError(Exception):
    pass


def _authenticateAdmin(adminInstitutionalId: str, adminPin: str) -> dict[str, Any]:
    admin = authenticateBadgeHolder(adminInstitutionalId, adminPin)

    if admin["role"] != UserRole.admin.value:
        raise NotAnAdminError("Only an institutional admin can issue badges")

    return admin


def _findBadgeHolder(institutionalId: str) -> dict[str, Any]:
    holder = getDatabase().users.find_one(
        {"institutional_id": institutionalId},
        {"id": 1, "role": 1, "institutional_id": 1, "is_active": 1},
    )

    if not holder:
        raise BadgeHolderNotFoundError("Badge holder was not found")

    if not holder["is_active"]:
        raise BadgeHolderNotFoundError("Badge holder account is not active")

    return holder


def issueBadge(request: IssueBadgeRequest) -> dict:
    assertValidInstitutionalId(request.adminInstitutionalId)
    assertValidInstitutionalId(request.institutionalId)

    admin = _authenticateAdmin(request.adminInstitutionalId, request.adminPin)
    holder = _findBadgeHolder(request.institutionalId)

    database = getDatabase()
    previousBadge = findCurrentBadge(holder["id"], {"id": 1})

    issuedAtDate = datetime.now(timezone.utc)
    issuedAt = issuedAtDate.isoformat()
    validUntil = (issuedAtDate + timedelta(days=request.validForDays)).isoformat()
    roleType = (request.roleType or UserRole(holder["role"])).value

    badgeDocument = {
        "id": getNextSequence("badges"),
        "user_id": holder["id"],
        "badge_code": (
            f"BADGE-{holder['institutional_id']}-{uuid.uuid4().hex[:8].upper()}"
        ),
        "role_type": roleType,
        "status": "issued",
        "issued_at": issuedAt,
        "valid_from": issuedAt,
        "valid_until": validUntil,
        "issued_by_user_id": admin["id"],
        "issuing_authority": getIssuingAuthority(),
    }
    database.badges.insert_one(badgeDocument)

    if previousBadge:
        database.badges.update_one(
            {"id": previousBadge["id"]},
            {"$set": {"status": "superseded", "superseded_at": issuedAt}},
        )

    # A device must never install a badge that was replaced before it synced.
    supersedePendingDeliveries(holder["id"])
    delivery = triggerBadgeDelivery(holder["id"], badgeDocument)

    return {
        "message": "Badge issued successfully",
        "badge": {
            "id": badgeDocument["id"],
            "userId": holder["id"],
            "badgeCode": badgeDocument["badge_code"],
            "roleType": roleType,
            "status": badgeDocument["status"],
            "issuedAt": issuedAt,
            "validFrom": issuedAt,
            "validUntil": validUntil,
        },
        "supersededBadgeId": previousBadge["id"] if previousBadge else None,
        "delivery": delivery,
    }


def fetchPendingBadgeDeliveries(institutionalId: str, pin: str) -> dict:
    assertValidInstitutionalId(institutionalId)
    holder = authenticateBadgeHolder(institutionalId, pin)

    return {
        "institutionalId": institutionalId,
        "deliveries": listPendingDeliveries(holder["id"]),
    }


def acknowledgeBadgeDelivery(
    institutionalId: str,
    deliveryId: str,
    pin: str,
) -> dict:
    assertValidInstitutionalId(institutionalId)
    holder = authenticateBadgeHolder(institutionalId, pin)

    return acknowledgeDelivery(holder["id"], deliveryId)
