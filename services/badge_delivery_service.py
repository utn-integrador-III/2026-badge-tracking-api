import uuid
from datetime import datetime, timezone
from typing import Any

from pymongo import ReturnDocument

from database.connection import getDatabase
from models.user import BadgeDeliveryStatus


class BadgeDeliveryNotFoundError(Exception):
    pass


ACTIVE_DELIVERY_BADGE_STATUSES = frozenset({"issued", "active"})


def _toDeliveryResponse(delivery: dict[str, Any]) -> dict:
    return {
        "deliveryId": delivery["delivery_id"],
        "badgeId": delivery["badge_id"],
        "badgeCode": delivery["badge_code"],
        "roleType": delivery["role_type"],
        "status": delivery["status"],
        "validFrom": delivery["valid_from"],
        "validUntil": delivery["valid_until"],
        "triggeredAt": delivery["triggered_at"],
        "deliveredAt": delivery.get("delivered_at"),
    }


def supersedePendingDeliveries(userId: int) -> None:
    getDatabase().badge_deliveries.update_many(
        {"user_id": userId, "status": BadgeDeliveryStatus.pending.value},
        {"$set": {"status": BadgeDeliveryStatus.superseded.value}},
    )


def cancelPendingBadgeDeliveries(badgeId: int, reason: str) -> None:
    cancelledAt = datetime.now(timezone.utc).isoformat()
    getDatabase().badge_deliveries.update_many(
        {"badge_id": badgeId, "status": BadgeDeliveryStatus.pending.value},
        {
            "$set": {
                "status": BadgeDeliveryStatus.cancelled.value,
                "cancelled_at": cancelledAt,
                "cancellation_reason": reason,
            }
        },
    )


def triggerBadgeDelivery(userId: int, badge: dict[str, Any]) -> dict:
    triggeredAt = datetime.now(timezone.utc).isoformat()
    delivery = {
        "delivery_id": uuid.uuid4().hex,
        "badge_id": badge["id"],
        "user_id": userId,
        "badge_code": badge["badge_code"],
        "role_type": badge["role_type"],
        "status": BadgeDeliveryStatus.pending.value,
        "valid_from": badge["valid_from"],
        "valid_until": badge["valid_until"],
        "triggered_at": triggeredAt,
        "delivered_at": None,
    }
    getDatabase().badge_deliveries.insert_one(delivery)

    return _toDeliveryResponse(delivery)


def listPendingDeliveries(userId: int) -> list[dict]:
    database = getDatabase()
    deliveries = list(
        database.badge_deliveries.find(
            {"user_id": userId, "status": BadgeDeliveryStatus.pending.value},
        )
    )

    badgeIds = [delivery["badge_id"] for delivery in deliveries]
    activeBadgeIds = {
        badge["id"]
        for badge in database.badges.find(
            {
                "id": {"$in": badgeIds},
                "status": {"$in": list(ACTIVE_DELIVERY_BADGE_STATUSES)},
            },
            {"id": 1},
        )
    }

    for delivery in deliveries:
        if delivery["badge_id"] not in activeBadgeIds:
            cancelPendingBadgeDeliveries(
                delivery["badge_id"],
                "Badge is no longer active",
            )

    return [
        _toDeliveryResponse(delivery)
        for delivery in sorted(deliveries, key=lambda item: item["triggered_at"])
        if delivery["badge_id"] in activeBadgeIds
    ]


def _badgeWasInactiveWhenDelivered(delivery: dict[str, Any]) -> bool:
    badge = getDatabase().badges.find_one(
        {"id": delivery["badge_id"]},
        {
            "status": 1,
            "status_changed_at": 1,
            "suspended_at": 1,
            "revoked_at": 1,
            "superseded_at": 1,
        },
    )
    if badge and badge["status"] in ACTIVE_DELIVERY_BADGE_STATUSES:
        return False

    inactiveAt = None
    if badge:
        inactiveAt = (
            badge.get("status_changed_at")
            or badge.get("suspended_at")
            or badge.get("revoked_at")
            or badge.get("superseded_at")
        )

    deliveredAt = delivery.get("delivered_at")
    if not inactiveAt or not deliveredAt:
        return True

    try:
        return datetime.fromisoformat(deliveredAt) >= datetime.fromisoformat(inactiveAt)
    except (TypeError, ValueError):
        return True


def _cancelInvalidDeliveryAcknowledgement(
    delivery: dict[str, Any],
) -> dict[str, Any]:
    if (
        delivery["status"] != BadgeDeliveryStatus.delivered.value
        or not _badgeWasInactiveWhenDelivered(delivery)
    ):
        return delivery

    database = getDatabase()
    cancelledDelivery = database.badge_deliveries.find_one_and_update(
        {
            "delivery_id": delivery["delivery_id"],
            "user_id": delivery["user_id"],
            "status": BadgeDeliveryStatus.delivered.value,
            "delivered_at": delivery["delivered_at"],
        },
        {
            "$set": {
                "status": BadgeDeliveryStatus.cancelled.value,
                "delivered_at": None,
                "cancelled_at": datetime.now(timezone.utc).isoformat(),
                "cancellation_reason": (
                    "Badge was inactive when delivery was acknowledged"
                ),
            }
        },
        return_document=ReturnDocument.AFTER,
    )
    if cancelledDelivery:
        return cancelledDelivery

    currentDelivery = database.badge_deliveries.find_one(
        {
            "delivery_id": delivery["delivery_id"],
            "user_id": delivery["user_id"],
        }
    )
    if not currentDelivery:
        raise BadgeDeliveryNotFoundError("Badge delivery was not found")
    return currentDelivery


def acknowledgeDelivery(userId: int, deliveryId: str) -> dict:
    database = getDatabase()
    deliveredAt = datetime.now(timezone.utc).isoformat()
    delivery = database.badge_deliveries.find_one_and_update(
        {
            "delivery_id": deliveryId,
            "user_id": userId,
            "status": BadgeDeliveryStatus.pending.value,
        },
        {
            "$set": {
                "status": BadgeDeliveryStatus.delivered.value,
                "delivered_at": deliveredAt,
            }
        },
        return_document=ReturnDocument.AFTER,
    )

    if delivery:
        return _toDeliveryResponse(_cancelInvalidDeliveryAcknowledgement(delivery))

    delivery = database.badge_deliveries.find_one(
        {"delivery_id": deliveryId, "user_id": userId}
    )

    if not delivery:
        raise BadgeDeliveryNotFoundError("Badge delivery was not found")

    return _toDeliveryResponse(_cancelInvalidDeliveryAcknowledgement(delivery))
