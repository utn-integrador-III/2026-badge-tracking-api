import importlib

import pytest
from fastapi.testclient import TestClient

@pytest.fixture()
def client(tmp_path, monkeypatch):
    databasePath = tmp_path / "badge_tracking_test.db"
    monkeypatch.setenv("BADGE_TRACKING_DB_PATH", str(databasePath))

    connectionModule = importlib.import_module("database.connection")
    connectionModule.initializeDatabase()

    mainModule = importlib.import_module("main")
    return TestClient(mainModule.app)

def registerUser(client, institutionalId: str = "123456789") -> None:
    client.post(
        "/users/institutional-identities",
        json={
            "fullName": "Kevin Picado",
            "email": f"{institutionalId}@utn.ac.cr",
            "role": "student",
            "institutionalId": institutionalId,
        },
    )

def setPin(
    client,
    institutionalId: str = "123456789",
    pin: str = "281992",
    pinConfirm: str | None = None,
) -> object:
    return client.post(
        f"/users/{institutionalId}/pin",
        json={"pin": pin, "pinConfirm": pinConfirm or pin},
    )

def validatePin(
    client,
    institutionalId: str = "123456789",
    pin: str = "281992",
) -> object:
    return client.post(
        f"/users/{institutionalId}/pin/validate",
        json={"pin": pin},
    )

class TestSetPin:
    def test_set_pin_successfully(self, client):
        registerUser(client)
        response = setPin(client)

        assert response.status_code == 201
        body = response.json()
        assert body["message"] == "PIN set successfully"
        assert body["institutionalId"] == "123456789"
        assert "pinSetAt" in body

    def test_set_pin_requires_existing_user(self, client):
        response = setPin(client, institutionalId="999999999")

        assert response.status_code == 404
        assert response.json()["detail"] == "User not found"

    def test_set_pin_rejects_duplicate(self, client):
        registerUser(client)
        setPin(client)

        response = setPin(client, pin="375849", pinConfirm="375849")

        assert response.status_code == 409
        assert "already been set" in response.json()["detail"]

    def test_set_pin_rejects_mismatched_pins(self, client):
        registerUser(client)
        response = setPin(client, pin="281992", pinConfirm="999999")

        assert response.status_code == 422
        assert "do not match" in response.json()["detail"]

    def test_set_pin_rejects_non_numeric_pin(self, client):
        registerUser(client)
        response = setPin(client, pin="abc123", pinConfirm="abc123")

        assert response.status_code == 422

    def test_set_pin_rejects_all_same_digits(self, client):
        registerUser(client)
        response = setPin(client, pin="111111", pinConfirm="111111")

        assert response.status_code == 422

    def test_set_pin_rejects_sequential_pin(self, client):
        registerUser(client)
        response = setPin(client, pin="123456", pinConfirm="123456")

        assert response.status_code == 422

    def test_set_pin_rejects_too_short(self, client):
        registerUser(client)
        response = setPin(client, pin="1234", pinConfirm="1234")

        assert response.status_code == 422

    def test_set_pin_rejects_too_long(self, client):
        registerUser(client)
        response = setPin(client, pin="123456789", pinConfirm="123456789")

        assert response.status_code == 422

    def test_set_pin_rejects_invalid_institutional_id_format(self, client):
        response = setPin(client, institutionalId="ABC-123")

        assert response.status_code == 422
        assert "9 digits" in response.json()["detail"]

class TestValidatePin:
    def test_validate_pin_successfully(self, client):
        registerUser(client)
        setPin(client)

        response = validatePin(client)

        assert response.status_code == 200
        body = response.json()
        assert body["valid"] is True
        assert body["institutionalId"] == "123456789"
        assert body["message"] == "PIN validated successfully"

    def test_validate_pin_rejects_wrong_pin(self, client):
        registerUser(client)
        setPin(client, pin="281992")

        response = validatePin(client, pin="999999")

        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid PIN"

    def test_validate_pin_rejects_unknown_user(self, client):
        response = validatePin(client, institutionalId="999999999")

        assert response.status_code == 404
        assert response.json()["detail"] == "User not found"

    def test_validate_pin_requires_pin_to_be_set_first(self, client):
        registerUser(client)

        response = validatePin(client)

        assert response.status_code == 409
        assert "No PIN has been set" in response.json()["detail"]

    def test_validate_pin_rejects_non_numeric_input(self, client):
        registerUser(client)
        setPin(client)

        response = validatePin(client, pin="abcdef")

        assert response.status_code == 422

    def test_validate_pin_rejects_invalid_institutional_id_format(self, client):
        response = validatePin(client, institutionalId="ABC-123")

        assert response.status_code == 422
        assert "9 digits" in response.json()["detail"]

    def test_validate_pin_rejects_too_short(self, client):
        registerUser(client)
        setPin(client)

        response = validatePin(client, pin="12345")

        assert response.status_code == 422

    def test_correct_pin_after_wrong_attempt(self, client):
        registerUser(client)
        setPin(client, pin="281992")

        wrongResponse = validatePin(client, pin="000000")
        correctResponse = validatePin(client, pin="281992")

        assert wrongResponse.status_code == 401
        assert correctResponse.status_code == 200
        assert correctResponse.json()["valid"] is True

    def test_two_users_each_validate_their_own_pin(self, client):
        registerUser(client, institutionalId="111111111")
        registerUser(client, institutionalId="222222222")
        setPin(client, institutionalId="111111111", pin="281992")
        setPin(client, institutionalId="222222222", pin="375849")

        response = validatePin(client, institutionalId="111111111", pin="375849")

        assert response.status_code == 401

    def test_pin_is_not_stored_in_plain_text(self, client):
        registerUser(client)
        setPin(client, pin="281992")

        profile = client.get("/users/123456789/badge-profile")

        assert profile.status_code == 200
        assert "pin" not in profile.json()
        assert "pinHash" not in profile.json()
        assert "pin_hash" not in profile.json()