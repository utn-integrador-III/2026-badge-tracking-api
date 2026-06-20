import os
import sqlite3
from contextlib import closing
from pathlib import Path


def getDatabasePath() -> Path:
    configuredPath = os.getenv("BADGE_TRACKING_DB_PATH")
    if configuredPath:
        return Path(configuredPath)

    return Path(__file__).resolve().parent / "badge_tracking.db"


def getConnection() -> sqlite3.Connection:
    databasePath = getDatabasePath()
    databasePath.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(databasePath)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initializeDatabase() -> None:
    with closing(getConnection()) as connection:
        with connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    full_name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    role TEXT NOT NULL CHECK(role IN ('student', 'professor', 'staff')),
                    institutional_id TEXT NOT NULL UNIQUE,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS badges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL UNIQUE,
                    badge_code TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL DEFAULT 'issued',
                    issued_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );
                """
            )
