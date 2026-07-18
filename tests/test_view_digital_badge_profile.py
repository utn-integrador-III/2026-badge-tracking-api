from datetime import datetime


def registerUser(client):
    return client.post(
        "/users/institutional-identities",
        json={
            "fullName": "Test User",
            "email": "test.user@utn.ac.cr",
            "role": "student",
            "institutionalId": "123456789",
            "photoUrl": "https://example.com/profile-photo.png",
        },
    )


def test_get_digital_badge_profile_returns_badge_holder_information(client):
    registerResponse = registerUser(client)

    response = client.get("/users/123456789/badge-profile")

    assert registerResponse.status_code == 201
    assert response.status_code == 200

    body = response.json()
    assert body["photoUrl"] == "https://example.com/profile-photo.png"
    assert body["fullName"] == "Test User"
    assert body["role"] == "student"
    assert body["institutionalId"] == "123456789"
    assert body["badgeCode"].startswith("BADGE-123456789-")
    assert body["status"] == "issued"
    assert datetime.fromisoformat(body["validUntil"]) > datetime.fromisoformat(
        body["validFrom"]
    )


def test_get_digital_badge_profile_rejects_invalid_institutional_id(client):
    response = client.get("/users/ABC-123/badge-profile")

    assert response.status_code == 422
    assert response.json()["detail"] == "Institutional ID must contain exactly 9 digits"


def test_get_digital_badge_profile_returns_not_found_for_missing_user(client):
    response = client.get("/users/999999999/badge-profile")

    assert response.status_code == 404
    assert response.json()["detail"] == "Badge profile was not found"
