import importlib
import uuid

import mongomock
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    databaseName = f"badge_tracking_test_{uuid.uuid4().hex}"
    connectionModule = importlib.import_module("database.connection")

    connectionModule.closeDatabase()
    monkeypatch.setenv("BADGE_TRACKING_MONGODB_URI", "mongodb://localhost")
    monkeypatch.setenv("BADGE_TRACKING_MONGODB_DATABASE", databaseName)
    monkeypatch.setattr(connectionModule, "MongoClient", mongomock.MongoClient)
    connectionModule.initializeDatabase()

    mainModule = importlib.import_module("main")
    with TestClient(mainModule.app) as testClient:
        yield testClient

    connectionModule.getClient().drop_database(databaseName)
    connectionModule.closeDatabase()


@pytest.fixture()
def mongoDatabase(client):
    connectionModule = importlib.import_module("database.connection")
    return connectionModule.getDatabase()
