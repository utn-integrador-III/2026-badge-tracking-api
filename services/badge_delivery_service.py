import uuid
from datetime import datetime, timezone
from typing import Any

from database.connection import getDatabase
from models.user import BadgeDeliveryStatus


class BadgeDeliveryNotFoundError(Exception):
    pass


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
    deliveries = getDatabase().badge_deliveries.find(
        {"user_id": userId, "status": BadgeDeliveryStatus.pending.value},
    )

    return [
        _toDeliveryResponse(delivery)
        for delivery in sorted(deliveries, key=lambda item: item["triggered_at"])
    ]


def acknowledgeDelivery(userId: int, deliveryId: str) -> dict:
    database = getDatabase()
    delivery = database.badge_deliveries.find_one(
        {"delivery_id": deliveryId, "user_id": userId}
    )

    if not delivery:
        raise BadgeDeliveryNotFoundError("Badge delivery was not found")

    if delivery["status"] == BadgeDeliveryStatus.pending.value:
        delivery["status"] = BadgeDeliveryStatus.delivered.value
        delivery["delivered_at"] = datetime.now(timezone.utc).isoformat()
        database.badge_deliveries.update_one(
            {"delivery_id": deliveryId},
            {
                "$set": {
                    "status": delivery["status"],
                    "delivered_at": delivery["delivered_at"],
                }
            },
        )

    return _toDeliveryResponse(delivery)
