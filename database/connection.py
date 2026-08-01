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
    database.badges.create_index(
        [("user_id", ASCENDING)],
        unique=True,
        name="unique_badge_user_id",
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


def closeDatabase() -> None:
    if getClient.cache_info().currsize:
        getClient().close()
        getClient.cache_clear()
