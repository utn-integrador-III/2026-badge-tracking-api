import os
from functools import lru_cache

from pymongo import ASCENDING, MongoClient
from pymongo.database import Database


DEFAULT_MONGODB_URI = "mongodb://localhost:27017"
DEFAULT_DATABASE_NAME = "badge_tracking"


def getMongoUri() -> str:
    return os.getenv("BADGE_TRACKING_MONGODB_URI", DEFAULT_MONGODB_URI)


def getDatabaseName() -> str:
    return os.getenv("BADGE_TRACKING_MONGODB_DATABASE", DEFAULT_DATABASE_NAME)


@lru_cache
def getClient() -> MongoClient:
    return MongoClient(getMongoUri())


def getDatabase() -> Database:
    return getClient()[getDatabaseName()]


def initializeDatabase() -> None:
    database = getDatabase()

    database.users.create_index(
        [("email", ASCENDING)],
        unique=True,
        name="unique_user_email",
    )
    database.users.create_index(
        [("institutional_id", ASCENDING)],
        unique=True,
        name="unique_user_institutional_id",
    )
    database.users.create_index(
        [("id", ASCENDING)],
        unique=True,
        name="unique_user_id",
    )
    # A user accumulates badges as admins reissue them, so this is not unique.
    database.badges.create_index(
        [("user_id", ASCENDING), ("status", ASCENDING)],
        name="badge_user_status",
    )
    database.badges.create_index(
        [("badge_code", ASCENDING)],
        unique=True,
        name="unique_badge_code",
    )
    database.badges.create_index(
        [("id", ASCENDING)],
        unique=True,
        name="unique_badge_id",
    )
    database.age_proof_tokens.create_index(
        [("token_hash", ASCENDING)],
        unique=True,
        name="unique_age_proof_token_hash",
    )
    database.age_proof_tokens.create_index(
        [("user_id", ASCENDING), ("expires_at", ASCENDING)],
        name="age_proof_token_user_expiry",
    )
    database.badge_verifications.create_index(
        [("verification_id", ASCENDING)],
        unique=True,
        name="unique_badge_verification_id",
    )
    database.badge_verifications.create_index(
        [("user_id", ASCENDING), ("verified_at", ASCENDING)],
        name="badge_verification_user_time",
    )
    database.badge_deliveries.create_index(
        [("delivery_id", ASCENDING)],
        unique=True,
        name="unique_badge_delivery_id",
    )
    database.badge_deliveries.create_index(
        [("user_id", ASCENDING), ("status", ASCENDING)],
        name="badge_delivery_user_status",
    )
    database.badge_deliveries.create_index(
        [("badge_id", ASCENDING), ("status", ASCENDING)],
        name="badge_delivery_badge_status",
    )
    database.institution_branding.create_index(
        [("institution", ASCENDING)],
        unique=True,
        name="unique_institution_branding",
    )
    database.institution_branding.create_index(
        [("logo_asset_id", ASCENDING)],
        name="institution_branding_logo_asset",
    )
    database.badge_notifications.create_index(
        [("notification_id", ASCENDING)],
        unique=True,
        name="unique_badge_notification_id",
    )
    # A badge is warned about once, so a notice the holder dealt with cannot be
    # queued again on the next scan.
    database.badge_notifications.create_index(
        [("badge_id", ASCENDING), ("type", ASCENDING)],
        unique=True,
        name="unique_badge_notification_per_badge",
    )
    database.badge_notifications.create_index(
        [("user_id", ASCENDING), ("status", ASCENDING)],
        name="badge_notification_user_status",
    )
    database.badge_renewal_requests.create_index(
        [("request_id", ASCENDING)],
        unique=True,
        name="unique_badge_renewal_request_id",
    )
    # Only one renewal request of a badge can be open at a time.
    database.badge_renewal_requests.create_index(
        [("badge_id", ASCENDING), ("status", ASCENDING)],
        unique=True,
        name="unique_badge_renewal_request_per_badge_status",
    )
    database.badge_renewal_requests.create_index(
        [("user_id", ASCENDING), ("status", ASCENDING)],
        name="badge_renewal_request_user_status",
    )


def closeDatabase() -> None:
    if getClient.cache_info().currsize:
        getClient().close()
        getClient.cache_clear()
