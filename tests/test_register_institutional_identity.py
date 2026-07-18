from datetime import datetime, timedelta

import pytest


def validPayload(**overrides):
    payload = {
        "fullName": "Kevin Picado",
        "email": "kevin.picado@utn.ac.cr",
        "role": "student",
        "institutionalId": "123456789",
    }
    payload.update(overrides)
    return payload


def test_register_user_successfully_issues_badge(client):
    response = client.post("/users/institutional-identities", json=validPayload())

    assert response.status_code == 201
    body = response.json()
    assert body["message"] == "User registered successfully"
    assert body["user"]["email"] == "kevin.picado@utn.ac.cr"
    assert body["user"]["institutionalId"] == "123456789"
    assert body["user"]["isActive"] is True
    assert body["badge"]["status"] == "issued"
    assert body["badge"]["badgeCode"].startswith("BADGE-123456789-")


def test_register_user_persists_documents_in_mongodb(client, mongoDatabase):
    response = client.post("/users/institutional-identities", json=validPayload())

    assert response.status_code == 201

    user = mongoDatabase.users.find_one({"institutional_id": "123456789"})
    badge = mongoDatabase.badges.find_one({"user_id": user["id"]})

    assert user["full_name"] == "Kevin Picado"
    assert user["email"] == "kevin.picado@utn.ac.cr"
    assert user["is_active"] is True
    assert badge["badge_code"].startswith("BADGE-123456789-")
    assert badge["valid_from"] == response.json()["badge"]["validFrom"]


def test_register_user_rejects_duplicate_institutional_id(client):
    firstResponse = client.post("/users/institutional-identities", json=validPayload())
    secondResponse = client.post(
        "/users/institutional-identities",
        json=validPayload(email="other.user@utn.ac.cr"),
    )

    assert firstResponse.status_code == 201
    assert secondResponse.status_code == 409
    assert secondResponse.json()["detail"] == "Institutional ID is already registered"


def test_register_user_rejects_duplicate_email(client):
    firstResponse = client.post("/users/institutional-identities", json=validPayload())
    secondResponse = client.post(
        "/users/institutional-identities",
        json=validPayload(institutionalId="987654321"),
    )

    assert firstResponse.status_code == 201
    assert secondResponse.status_code == 409
    assert secondResponse.json()["detail"] == "Email is already registered"


def test_register_user_requires_valid_role(client):
    response = client.post(
        "/users/institutional-identities",
        json=validPayload(role="guest"),
    )

    assert response.status_code == 422


def test_register_user_requires_nine_digit_institutional_id(client):
    response = client.post(
        "/users/institutional-identities",
        json=validPayload(institutionalId="ABC-123"),
    )

    assert response.status_code == 422


@pytest.mark.parametrize("role", ["student", "professor", "staff"])
def test_register_user_accepts_all_valid_roles(client, role):
    response = client.post(
        "/users/institutional-identities",
        json=validPayload(role=role, institutionalId="111111111"),
    )

    assert response.status_code == 201
    assert response.json()["user"]["role"] == role


def test_register_user_normalizes_email_to_lowercase(client):
    response = client.post(
        "/users/institutional-identities",
        json=validPayload(email="Kevin.Picado@UTN.AC.CR"),
    )

    assert response.status_code == 201
    assert response.json()["user"]["email"] == "kevin.picado@utn.ac.cr"


def test_register_user_trims_whitespace_in_text_fields(client):
    response = client.post(
        "/users/institutional-identities",
        json=validPayload(fullName="  Kevin Picado  "),
    )

    assert response.status_code == 201
    assert response.json()["user"]["fullName"] == "Kevin Picado"


def test_register_user_rejects_invalid_email_format(client):
    response = client.post(
        "/users/institutional-identities",
        json=validPayload(email="not-an-email"),
    )

    assert response.status_code == 422


def test_register_user_rejects_full_name_too_short(client):
    response = client.post(
        "/users/institutional-identities",
        json=validPayload(fullName="K"),
    )

    assert response.status_code == 422


def test_register_user_rejects_missing_required_field(client):
    payload = validPayload()
    del payload["fullName"]

    response = client.post("/users/institutional-identities", json=payload)

    assert response.status_code == 422


def test_register_user_accepts_optional_photo_url_omitted(client):
    response = client.post("/users/institutional-identities", json=validPayload())

    assert response.status_code == 201
    assert response.json()["user"]["photoUrl"] is None


def test_register_user_issues_badge_valid_for_one_year(client):
    response = client.post("/users/institutional-identities", json=validPayload())

    assert response.status_code == 201
    badge = response.json()["badge"]
    issuedAt = datetime.fromisoformat(badge["issuedAt"])
    validUntil = datetime.fromisoformat(badge["validUntil"])

    assert (validUntil - issuedAt) == timedelta(days=365)


def test_root_returns_api_information(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "message": "Badge Tracking API is running",
        "docs": "/docs",
    }
