"""Queue the renewal notice of every badge that entered the expiry window.

Run it on a daily schedule so holders are warned even when their device does
not sync:

    python -m jobs.expiry_notifications
"""

from datetime import datetime, timedelta, timezone

from database.connection import getDatabase
from services.badge_notification_service import (
    evaluateExpiryNotifications,
    getExpiryNoticeInDays,
)
from services.user_service import ACTIVE_BADGE_STATUSES


def scanForExpiringBadges(reference: datetime | None = None) -> dict[str, int]:
    """Warn the holder of every active badge that is about to expire.

    Returns how many badges were examined and how many notifications the scan
    queued. Running it twice a day does not warn anybody twice.
    """
    reference = reference or datetime.now(timezone.utc)
    cutoff = (reference + timedelta(days=getExpiryNoticeInDays())).isoformat()
    database = getDatabase()

    badges = database.badges.find(
        {
            "status": {"$in": list(ACTIVE_BADGE_STATUSES)},
            "$or": [
                {"valid_until": {"$lte": cutoff}},
                # Badges predating the validity fields fall back to a computed
                # expiry, so they are examined instead of skipped.
                {"valid_until": {"$exists": False}},
                {"valid_until": None},
            ],
        },
        {"user_id": 1},
    )

    scannedBadges = 0
    queuedNotifications = 0
    for badge in badges:
        user = database.users.find_one(
            {"id": badge["user_id"], "is_active": True},
            {"id": 1, "institutional_id": 1},
        )
        if not user:
            continue

        scannedBadges += 1
        if evaluateExpiryNotifications(user, reference):
            queuedNotifications += 1

    return {"scanned": scannedBadges, "queued": queuedNotifications}


def main() -> None:
    summary = scanForExpiringBadges()
    print(
        f"Expiry scan examined {summary['scanned']} badge(s) and queued "
        f"{summary['queued']} notification(s)."
    )


if __name__ == "__main__":
    main()
