import math
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from database.connection import getDatabase
from models.user import (
    BadgeNotificationStatus,
    BadgeNotificationType,
    BadgeRenewalRequestStatus,
)
from services.user_service import (
    assertValidInstitutionalId,
    authenticateBadgeHolder,
    calculateDefaultValidUntil,
    findCurrentBadge,
    getVerificationBaseUrl,
)


class BadgeNotificationNotFoundError(Exception):
    pass


class NoRenewableBadgeError(Exception):
    pass


DEFAULT_EXPIRY_NOTICE_IN_DAYS = 30
MAX_EXPIRY_NOTICE_IN_DAYS = 365
RENEWAL_ACTION_LABEL = "Renew badge"
RENEWAL_REQUESTED_REASON = "Renewal requested by the badge holder"

# A notification the holder has not dealt with yet, so it still needs to reach
# the device or wait for the renewal it asks for.
OPEN_NOTIFICATION_STATUSES = frozenset(
    {
        BadgeNotificationStatus.pending.value,
        BadgeNotificationStatus.delivered.value,
    }
)

_EXPIRY_BADGE_FIELDS = {
    "id": 1,
    "user_id": 1,
    "badge_code": 1,
    "status": 1,
    "issued_at": 1,
    "valid_from": 1,
    "valid_until": 1,
}


def getExpiryNoticeInDays() -> int:
    """Return how many days before expiry the holder is warned."""
    configuredDays = os.getenv("BADGE_TRACKING_EXPIRY_NOTICE_DAYS", "").strip()
    if not configuredDays:
        return DEFAULT_EXPIRY_NOTICE_IN_DAYS

    try:
        noticeDays = int(configuredDays)
    except ValueError:
        return DEFAULT_EXPIRY_NOTICE_IN_DAYS

    if not 1 <= noticeDays <= MAX_EXPIRY_NOTICE_IN_DAYS:
        return DEFAULT_EXPIRY_NOTICE_IN_DAYS

    return noticeDays


def _parseTimestamp(value: Any) -> datetime | None:
    try:
        parsedValue = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None

    if parsedValue.tzinfo is None:
        return parsedValue.replace(tzinfo=timezone.utc)

    return parsedValue


def _badgeExpiry(badge: dict[str, Any]) -> tuple[str, datetime | None]:
    validFrom = badge.get("valid_from") or badge["issued_at"]
    validUntil = badge.get("valid_until") or calculateDefaultValidUntil(validFrom)
    return validUntil, _parseTimestamp(validUntil)


def _daysUntilExpiry(expiresAt: datetime | None, reference: datetime) -> int:
    if not expiresAt:
        return 0

    remainingTime = expiresAt - reference
    if remainingTime <= timedelta(0):
        return 0

    return math.ceil(remainingTime / timedelta(days=1))


def _describeRemainingDays(daysUntilExpiry: int) -> str:
    if daysUntilExpiry <= 0:
        return "today"
    if daysUntilExpiry == 1:
        return "in 1 day"
    return f"in {daysUntilExpiry} days"


def _buildRenewalActionUrl(institutionalId: str) -> str:
    return f"{getVerificationBaseUrl()}/users/{institutionalId}/badge-renewals"


def _buildExpiryTitle(daysUntilExpiry: int, expired: bool) -> str:
    if expired:
        return "Your badge has expired"
    return f"Your badge expires {_describeRemainingDays(daysUntilExpiry)}"


def _buildExpiryBody(
    badgeCode: str,
    expiresAt: datetime | None,
    daysUntilExpiry: int,
    expired: bool,
) -> str:
    expiryDate = expiresAt.date().isoformat() if expiresAt else "an unknown date"
    if expired:
        return (
            f"Badge {badgeCode} expired on {expiryDate}. "
            "Request a renewal to keep using your digital badge."
        )

    return (
        f"Badge {badgeCode} expires {_describeRemainingDays(daysUntilExpiry)} "
        f"on {expiryDate}. Request a renewal to keep using your digital badge."
    )


def _toNotificationResponse(
    notification: dict[str, Any],
    reference: datetime | None = None,
) -> dict:
    reference = reference or datetime.now(timezone.utc)
    validUntil = notification["valid_until"]
    expiresAt = _parseTimestamp(validUntil)
    daysUntilExpiry = _daysUntilExpiry(expiresAt, reference)
    expired = bool(expiresAt) and expiresAt <= reference

    # The device pulls the payload when it syncs, so the countdown is built on
    # read and never shows a figure that went stale in the queue.
    return {
        "notificationId": notification["notification_id"],
        "type": notification["type"],
        "status": notification["status"],
        "badgeId": notification["badge_id"],
        "badgeCode": notification["badge_code"],
        "title": _buildExpiryTitle(daysUntilExpiry, expired),
        "body": _buildExpiryBody(
            notification["badge_code"],
            expiresAt,
            daysUntilExpiry,
            expired,
        ),
        "actionLabel": RENEWAL_ACTION_LABEL,
        "actionUrl": notification["action_url"],
        "daysUntilExpiry": daysUntilExpiry,
        "expired": expired,
        "validUntil": validUntil,
        "createdAt": notification["created_at"],
        "deliveredAt": notification.get("delivered_at"),
    }


def _toRenewalRequestResponse(
    renewalRequest: dict[str, Any],
    reference: datetime | None = None,
) -> dict:
    reference = reference or datetime.now(timezone.utc)
    validUntil = renewalRequest["valid_until"]

    return {
        "requestId": renewalRequest["request_id"],
        "badgeId": renewalRequest["badge_id"],
        "badgeCode": renewalRequest["badge_code"],
        "status": renewalRequest["status"],
        "validUntil": validUntil,
        "daysUntilExpiry": _daysUntilExpiry(_parseTimestamp(validUntil), reference),
        "requestedAt": renewalRequest["requested_at"],
        "fulfilledAt": renewalRequest.get("fulfilled_at"),
        "fulfilledBadgeId": renewalRequest.get("fulfilled_badge_id"),
    }


def _resolveOutdatedNotifications(
    userId: int,
    currentBadgeId: int | None,
    reason: str,
) -> None:
    criteria: dict[str, Any] = {
        "user_id": userId,
        "status": {"$in": list(OPEN_NOTIFICATION_STATUSES)},
    }
    if currentBadgeId is not None:
        criteria["badge_id"] = {"$ne": currentBadgeId}

    getDatabase().badge_notifications.update_many(
        criteria,
        {
            "$set": {
                "status": BadgeNotificationStatus.resolved.value,
                "resolved_at": datetime.now(timezone.utc).isoformat(),
                "resolution_reason": reason,
            }
        },
    )


def _createExpiryNotification(
    user: dict[str, Any],
    badge: dict[str, Any],
    validUntil: str,
    reference: datetime,
) -> bool:
    notification = {
        "notification_id": uuid.uuid4().hex,
        "user_id": user["id"],
        "institutional_id": user["institutional_id"],
        "badge_id": badge["id"],
        "badge_code": badge["badge_code"],
        "type": BadgeNotificationType.badgeExpiring.value,
        "status": BadgeNotificationStatus.pending.value,
        "valid_until": validUntil,
        "notice_days": getExpiryNoticeInDays(),
        "action_url": _buildRenewalActionUrl(user["institutional_id"]),
        "created_at": reference.isoformat(),
        "delivered_at": None,
    }

    try:
        getDatabase().badge_notifications.insert_one(notification)
    except DuplicateKeyError:
        # The holder was already warned about this badge, and a warning they
        # dealt with must not come back on the next sync.
        return False

    return True


def evaluateExpiryNotifications(
    user: dict[str, Any],
    reference: datetime | None = None,
) -> bool:
    """Queue the expiry notice for a holder's badge once it enters the window.

    Returns whether a new notification was created. Calling this repeatedly is
    safe: a badge is only ever warned about once.
    """
    reference = reference or datetime.now(timezone.utc)
    badge = findCurrentBadge(user["id"], _EXPIRY_BADGE_FIELDS)

    if not badge:
        _resolveOutdatedNotifications(user["id"], None, "Badge is no longer active")
        return False

    _resolveOutdatedNotifications(
        user["id"],
        badge["id"],
        "Badge was replaced by a newer one",
    )

    validUntil, expiresAt = _badgeExpiry(badge)
    if not expiresAt:
        return False

    if expiresAt - reference > timedelta(days=getExpiryNoticeInDays()):
        return False

    if expiresAt <= reference:
        # An already expired badge is a lapse to recover from, not something to
        # warn about in advance.
        return False

    return _createExpiryNotification(user, badge, validUntil, reference)


def cancelBadgeNotifications(badgeId: int, reason: str) -> None:
    """Close the expiry notice and renewal request of a badge that lost validity."""
    database = getDatabase()
    changedAt = datetime.now(timezone.utc).isoformat()

    database.badge_notifications.update_many(
        {"badge_id": badgeId, "status": {"$in": list(OPEN_NOTIFICATION_STATUSES)}},
        {
            "$set": {
                "status": BadgeNotificationStatus.resolved.value,
                "resolved_at": changedAt,
                "resolution_reason": reason,
            }
        },
    )
    database.badge_renewal_requests.update_many(
        {"badge_id": badgeId, "status": BadgeRenewalRequestStatus.requested.value},
        {
            "$set": {
                "status": BadgeRenewalRequestStatus.cancelled.value,
                "cancelled_at": changedAt,
                "cancellation_reason": reason,
            }
        },
    )


def completeRenewal(userId: int, newBadge: dict[str, Any]) -> None:
    """Close what the previous badge left open once its replacement is issued."""
    _resolveOutdatedNotifications(
        userId,
        newBadge["id"],
        "Badge was renewed",
    )
    getDatabase().badge_renewal_requests.update_many(
        {
            "user_id": userId,
            "status": BadgeRenewalRequestStatus.requested.value,
            "badge_id": {"$ne": newBadge["id"]},
        },
        {
            "$set": {
                "status": BadgeRenewalRequestStatus.fulfilled.value,
                "fulfilled_at": datetime.now(timezone.utc).isoformat(),
                "fulfilled_badge_id": newBadge["id"],
            }
        },
    )


def fetchPendingNotifications(institutionalId: str, pin: str) -> dict:
    assertValidInstitutionalId(institutionalId)
    holder = authenticateBadgeHolder(institutionalId, pin)
    evaluateExpiryNotifications(holder)

    notifications = getDatabase().badge_notifications.find(
        {
            "user_id": holder["id"],
            "status": BadgeNotificationStatus.pending.value,
        }
    )
    reference = datetime.now(timezone.utc)

    return {
        "institutionalId": institutionalId,
        "notifications": [
            _toNotificationResponse(notification, reference)
            for notification in sorted(
                notifications,
                key=lambda item: item["created_at"],
            )
        ],
    }


def _findNotification(userId: int, notificationId: str) -> dict[str, Any]:
    notification = getDatabase().badge_notifications.find_one(
        {"notification_id": notificationId, "user_id": userId}
    )

    if not notification:
        raise BadgeNotificationNotFoundError("Badge notification was not found")

    return notification


def _changeNotificationStatus(
    userId: int,
    notificationId: str,
    fromStatuses: frozenset[str],
    toStatus: str,
    timestampField: str,
    extraFields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    changedAt = datetime.now(timezone.utc).isoformat()
    updatedFields = {"status": toStatus, timestampField: changedAt}
    updatedFields.update(extraFields or {})

    notification = getDatabase().badge_notifications.find_one_and_update(
        {
            "notification_id": notificationId,
            "user_id": userId,
            "status": {"$in": list(fromStatuses)},
        },
        {"$set": updatedFields},
        return_document=ReturnDocument.AFTER,
    )

    if notification:
        return notification

    return _findNotification(userId, notificationId)


def acknowledgeNotification(
    institutionalId: str,
    pin: str,
    notificationId: str,
) -> dict:
    assertValidInstitutionalId(institutionalId)
    holder = authenticateBadgeHolder(institutionalId, pin)

    notification = _changeNotificationStatus(
        holder["id"],
        notificationId,
        frozenset({BadgeNotificationStatus.pending.value}),
        BadgeNotificationStatus.delivered.value,
        "delivered_at",
    )

    return _toNotificationResponse(notification)


def dismissNotification(institutionalId: str, pin: str, notificationId: str) -> dict:
    assertValidInstitutionalId(institutionalId)
    holder = authenticateBadgeHolder(institutionalId, pin)

    notification = _changeNotificationStatus(
        holder["id"],
        notificationId,
        OPEN_NOTIFICATION_STATUSES,
        BadgeNotificationStatus.dismissed.value,
        "dismissed_at",
        {"dismissal_reason": "Dismissed by the badge holder"},
    )

    return _toNotificationResponse(notification)


def _dismissNotificationsForRenewal(userId: int, badgeId: int) -> None:
    getDatabase().badge_notifications.update_many(
        {
            "user_id": userId,
            "badge_id": badgeId,
            "status": {"$in": list(OPEN_NOTIFICATION_STATUSES)},
        },
        {
            "$set": {
                "status": BadgeNotificationStatus.dismissed.value,
                "dismissed_at": datetime.now(timezone.utc).isoformat(),
                "dismissal_reason": RENEWAL_REQUESTED_REASON,
            }
        },
    )


def requestBadgeRenewal(institutionalId: str, pin: str) -> dict:
    """Record the renewal the holder asked for through the notification CTA."""
    assertValidInstitutionalId(institutionalId)
    holder = authenticateBadgeHolder(institutionalId, pin)

    badge = findCurrentBadge(holder["id"], _EXPIRY_BADGE_FIELDS)
    if not badge:
        raise NoRenewableBadgeError("No active badge is available to renew")

    validUntil, _ = _badgeExpiry(badge)
    openRequest = {
        "badge_id": badge["id"],
        "status": BadgeRenewalRequestStatus.requested.value,
    }
    newRequestFields = {
        "request_id": uuid.uuid4().hex,
        "user_id": holder["id"],
        "institutional_id": institutionalId,
        "badge_code": badge["badge_code"],
        "valid_until": validUntil,
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "fulfilled_at": None,
        "fulfilled_badge_id": None,
    }

    database = getDatabase()
    try:
        renewalRequest = database.badge_renewal_requests.find_one_and_update(
            openRequest,
            {"$setOnInsert": newRequestFields},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError:
        # Two devices tapped the CTA at once; the request that landed first wins.
        renewalRequest = database.badge_renewal_requests.find_one(openRequest)
        if not renewalRequest:
            raise

    _dismissNotificationsForRenewal(holder["id"], badge["id"])

    return _toRenewalRequestResponse(renewalRequest)
