import re
import uuid
from datetime import datetime, timezone
from typing import Any

from pymongo import ASCENDING, ReturnDocument

from database.connection import getDatabase
from models.user import AdminBadgeSearchRequest, UpdateBadgeStatusRequest
from services.admin_service import authenticateAdmin
from services.badge_delivery_service import cancelPendingBadgeDeliveries
from services.user_service import calculateDefaultValidUntil, findLatestBadge


class BadgeNotFoundError(Exception):
    pass


class InvalidBadgeStatusTransitionError(Exception):
    pass


ALLOWED_BADGE_STATUS_TRANSITIONS = {
    "issued": frozenset({"suspended", "revoked"}),
    "active": frozenset({"suspended", "revoked"}),
    "suspended": frozenset({"revoked"}),
}


def _toBadgeResponse(
    badge: dict[str, Any],
    fallbackRole: str | None = None,
) -> dict:
    validFrom = badge.get("valid_from") or badge["issued_at"]
    validUntil = badge.get("valid_until") or calculateDefaultValidUntil(validFrom)
    roleType = badge.get("role_type") or fallbackRole
    if roleType is None:
        holder = getDatabase().users.find_one(
            {"id": badge["user_id"]},
            {"role": 1},
        )
        if not holder:
            raise BadgeNotFoundError("Badge holder was not found")
        roleType = holder["role"]

    return {
        "id": badge["id"],
        "userId": badge["user_id"],
        "badgeCode": badge["badge_code"],
        "roleType": roleType,
        "status": badge["status"],
        "issuedAt": badge["issued_at"],
        "validFrom": validFrom,
        "validUntil": validUntil,
    }


def searchBadgeHolders(request: AdminBadgeSearchRequest) -> dict:
    authenticateAdmin(request.adminInstitutionalId, request.adminPin)

    database = getDatabase()
    literalQuery = re.compile(re.escape(request.query), re.IGNORECASE)
    users = list(
        database.users.find(
            {
                "$or": [
                    {"institutional_id": literalQuery},
                    {"full_name": literalQuery},
                    {"email": literalQuery},
                ]
            },
            {
                "id": 1,
                "full_name": 1,
                "email": 1,
                "institutional_id": 1,
                "role": 1,
                "is_active": 1,
            },
        )
        .sort([("full_name", ASCENDING), ("id", ASCENDING)])
        .limit(request.limit)
    )

    results = []
    for user in users:
        badge = findLatestBadge(user["id"])
        results.append(
            {
                "userId": user["id"],
                "fullName": user["full_name"],
                "email": user["email"],
                "institutionalId": user["institutional_id"],
                "role": user["role"],
                "isActive": user["is_active"],
                "badge": _toBadgeResponse(badge, user["role"]) if badge else None,
            }
        )

    return {"count": len(results), "results": results}


def _buildStatusResponse(
    badge: dict[str, Any],
    previousStatus: str,
    changed: bool,
) -> dict:
    status = badge["status"]
    return {
        "message": (
            f"Badge {status} successfully"
            if changed
            else f"Badge is already {status}"
        ),
        "badge": _toBadgeResponse(badge),
        "previousStatus": previousStatus,
        "changed": changed,
        "changedAt": badge.get("status_changed_at")
        or badge.get(f"{status}_at")
        or badge["issued_at"],
        "reason": badge.get("status_change_reason")
        or badge.get(f"{status}_reason")
        or "Previously recorded status",
    }


def _returnIdempotentStatus(badge: dict[str, Any]) -> dict:
    cancelPendingBadgeDeliveries(
        badge["id"],
        badge.get("status_change_reason") or "Badge is no longer active",
    )
    return _buildStatusResponse(badge, badge["status"], changed=False)


def updateBadgeStatus(badgeId: int, request: UpdateBadgeStatusRequest) -> dict:
    admin = authenticateAdmin(request.adminInstitutionalId, request.adminPin)
    database = getDatabase()
    badge = database.badges.find_one({"id": badgeId})

    if not badge:
        raise BadgeNotFoundError("Badge was not found")

    targetStatus = request.status.value

    for attempt in range(2):
        previousStatus = badge["status"]

        if previousStatus == targetStatus:
            return _returnIdempotentStatus(badge)

        allowedTargets = ALLOWED_BADGE_STATUS_TRANSITIONS.get(
            previousStatus,
            frozenset(),
        )
        if targetStatus not in allowedTargets:
            raise InvalidBadgeStatusTransitionError(
                f"Badge status '{previousStatus}' cannot transition to "
                f"'{targetStatus}'"
            )

        changedAt = datetime.now(timezone.utc).isoformat()
        historyEvent = {
            "event_id": uuid.uuid4().hex,
            "previous_status": previousStatus,
            "status": targetStatus,
            "reason": request.reason,
            "changed_at": changedAt,
            "changed_by_user_id": admin["id"],
        }
        statusFields = {
            "status": targetStatus,
            "status_changed_at": changedAt,
            "status_changed_by_user_id": admin["id"],
            "status_change_reason": request.reason,
            f"{targetStatus}_at": changedAt,
            f"{targetStatus}_by_user_id": admin["id"],
            f"{targetStatus}_reason": request.reason,
        }
        updatedBadge = database.badges.find_one_and_update(
            {"id": badgeId, "status": previousStatus},
            {
                "$set": statusFields,
                "$push": {"status_history": historyEvent},
            },
            return_document=ReturnDocument.AFTER,
        )
        if updatedBadge:
            cancelPendingBadgeDeliveries(badgeId, request.reason)
            return _buildStatusResponse(
                updatedBadge,
                previousStatus,
                changed=True,
            )

        currentBadge = database.badges.find_one({"id": badgeId})
        if not currentBadge:
            raise BadgeNotFoundError("Badge was not found")
        if currentBadge["status"] == targetStatus:
            return _returnIdempotentStatus(currentBadge)

        shouldRetryTerminalRevocation = (
            attempt == 0
            and targetStatus == "revoked"
            and currentBadge["status"] == "suspended"
        )
        if not shouldRetryTerminalRevocation:
            raise InvalidBadgeStatusTransitionError(
                "Badge status changed while the request was being processed"
            )
        badge = currentBadge

    raise InvalidBadgeStatusTransitionError(
        "Badge status changed while the request was being processed"
    )
