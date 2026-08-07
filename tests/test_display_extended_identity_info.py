from datetime import date, datetime, timedelta, timezone

import pytest


HOLDER_ID = "123456789"
HOLDER_PIN = "281992"
ADMIN_ID = "900000001"
ADMIN_PIN = "481726"


def identityPayload(**overrides) -> dict:
    payload = {
        "fullName": "Kevin Picado",
        "email": "kevin.picado@utn.ac.cr",
        "role": "student",
        "institutionalId": HOLDER_ID,
        "photoUrl": "https://example.com/kevin.png",
        "birthDate": "1992-08-28",
        "nationality": "Costa Rican",
        "birthplace": "San Jose, Costa Rica",
        "documentExpiry": "2031-05-20",
    }
    payload.update(overrides)
    return payload


def registerIdentity(client, **overrides):
    return client.post(
        "/users/institutional-identities",
        json=identityPayload(**overrides),
    )


def setPin(client, institutionalId: str = HOLDER_ID, pin: str = HOLDER_PIN):
    return client.post(
        f"/users/{institutionalId}/pin",
        json={"pin": pin, "pinConfirm": pin},
    )


def getDetails(
    client,
    institutionalId: str = HOLDER_ID,
    pin: str = HOLDER_PIN,
):
    return client.post(
        f"/users/{institutionalId}/badge-profile/details",
        json={"pin": pin},
    )


def createHolder(client, **overrides) -> dict:
    registration = registerIdentity(client, **overrides)
    assert registration.status_code == 201
    assert setPin(client).status_code == 201
    return registration.json()


def createAdmin(client) -> None:
    response = registerIdentity(
        client,
        fullName="Institutional Administrator",
        email="admin@utn.ac.cr",
        role="admin",
        institutionalId=ADMIN_ID,
        photoUrl=None,
        birthDate=None,
        nationality=None,
        birthplace=None,
        documentExpiry=None,
    )
    assert response.status_code == 201
    assert setPin(client, ADMIN_ID, ADMIN_PIN).status_code == 201


class TestExtendedBadgeProfile:
    def test_holder_views_all_extended_credential_details(self, client):
        registration = createHolder(client)

        response = getDetails(client)

        assert response.status_code == 200
        body = response.json()
        assert body == {
            "photoUrl": "https://example.com/kevin.png",
            "fullName": "Kevin Picado",
            "role": "student",
            "institutionalId": HOLDER_ID,
            "badgeCode": registration["badge"]["badgeCode"],
            "roleType": "student",
            "status": "issued",
            "validFrom": registration["badge"]["validFrom"],
            "validUntil": registration["badge"]["validUntil"],
            "issuedAt": registration["badge"]["issuedAt"],
            "issuingAuthority": "Universidad Técnica Nacional",
            "nationality": "Costa Rican",
            "birthplace": "San Jose, Costa Rica",
            "documentExpiry": "2031-05-20",
        }
        assert datetime.fromisoformat(body["issuedAt"]).tzinfo is not None
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["Pragma"] == "no-cache"
        assert response.headers["Referrer-Policy"] == "no-referrer"

    def test_extended_identity_fields_are_persisted(self, client, mongoDatabase):
        createHolder(client)

        user = mongoDatabase.users.find_one({"institutional_id": HOLDER_ID})
        badge = mongoDatabase.badges.find_one({"user_id": user["id"]})

        assert user["nationality"] == "Costa Rican"
        assert user["birthplace"] == "San Jose, Costa Rica"
        assert user["document_expiry"] == "2031-05-20"
        assert badge["issuing_authority"] == "Universidad Técnica Nacional"

    def test_public_summary_does_not_expose_extended_identity_fields(self, client):
        createHolder(client)

        response = client.get(f"/users/{HOLDER_ID}/badge-profile")

        assert response.status_code == 200
        assert "nationality" not in response.json()
        assert "birthplace" not in response.json()
        assert "documentExpiry" not in response.json()
        assert "issuingAuthority" not in response.json()

    def test_details_do_not_expose_email_birth_date_or_pin_data(self, client):
        createHolder(client)

        response = getDetails(client)

        assert response.status_code == 200
        serializedBody = response.text
        assert "kevin.picado@utn.ac.cr" not in serializedBody
        assert "1992-08-28" not in serializedBody
        assert HOLDER_PIN not in serializedBody
        assert "pinHash" not in serializedBody

    def test_legacy_identity_returns_null_extended_fields(self, client):
        createHolder(
            client,
            nationality=None,
            birthplace=None,
            documentExpiry=None,
        )

        response = getDetails(client)

        assert response.status_code == 200
        assert response.json()["nationality"] is None
        assert response.json()["birthplace"] is None
        assert response.json()["documentExpiry"] is None

    def test_latest_reissued_badge_supplies_credential_metadata(
        self,
        client,
        monkeypatch,
    ):
        monkeypatch.setenv("BADGE_TRACKING_ISSUING_AUTHORITY", "Authority A")
        createAdmin(client)
        registration = createHolder(client)
        monkeypatch.setenv("BADGE_TRACKING_ISSUING_AUTHORITY", "Authority B")
        issued = client.post(
            "/badges",
            json={
                "adminInstitutionalId": ADMIN_ID,
                "adminPin": ADMIN_PIN,
                "institutionalId": HOLDER_ID,
                "roleType": "staff",
                "validForDays": 90,
            },
        )
        assert issued.status_code == 201

        response = getDetails(client)

        assert response.status_code == 200
        body = response.json()
        assert body["badgeCode"] == issued.json()["badge"]["badgeCode"]
        assert body["badgeCode"] != registration["badge"]["badgeCode"]
        assert body["roleType"] == "staff"
        assert body["issuedAt"] == issued.json()["badge"]["issuedAt"]
        assert body["issuingAuthority"] == "Authority B"

    def test_authority_is_preserved_after_configuration_changes(
        self,
        client,
        monkeypatch,
    ):
        monkeypatch.setenv("BADGE_TRACKING_ISSUING_AUTHORITY", "Original Authority")
        createHolder(client)
        monkeypatch.setenv("BADGE_TRACKING_ISSUING_AUTHORITY", "New Authority")

        response = getDetails(client)

        assert response.status_code == 200
        assert response.json()["issuingAuthority"] == "Original Authority"

    def test_legacy_badge_uses_configured_authority_fallback(
        self,
        client,
        mongoDatabase,
        monkeypatch,
    ):
        createHolder(client)
        mongoDatabase.badges.update_one(
            {"badge_code": {"$exists": True}},
            {"$unset": {"issuing_authority": ""}},
        )
        monkeypatch.setenv(
            "BADGE_TRACKING_ISSUING_AUTHORITY",
            "Legacy Authority",
        )

        response = getDetails(client)

        assert response.status_code == 200
        assert response.json()["issuingAuthority"] == "Legacy Authority"


class TestExtendedIdentityValidation:
    def test_registration_trims_extended_identity_fields(self, client):
        response = registerIdentity(
            client,
            nationality="  Costa Rican  ",
            birthplace="  San Jose  ",
            documentExpiry="  2031-05-20  ",
        )
        assert response.status_code == 201
        assert setPin(client).status_code == 201

        details = getDetails(client).json()

        assert details["nationality"] == "Costa Rican"
        assert details["birthplace"] == "San Jose"
        assert details["documentExpiry"] == "2031-05-20"

    @pytest.mark.parametrize(
        "documentExpiry",
        ["20-05-2031", "2031/05/20", "2031-02-29", "not-a-date"],
    )
    def test_registration_rejects_invalid_document_expiry(
        self,
        client,
        documentExpiry,
    ):
        response = registerIdentity(client, documentExpiry=documentExpiry)

        assert response.status_code == 422

    def test_past_document_expiry_is_preserved_for_display(self, client):
        expiredDate = (
            datetime.now(timezone.utc).date() - timedelta(days=1)
        ).isoformat()
        createHolder(client, documentExpiry=expiredDate)

        response = getDetails(client)

        assert response.status_code == 200
        assert response.json()["documentExpiry"] == expiredDate

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("nationality", "x"),
            ("nationality", "x" * 101),
            ("birthplace", "x"),
            ("birthplace", "x" * 151),
        ],
    )
    def test_registration_validates_extended_text_lengths(self, client, field, value):
        response = registerIdentity(client, **{field: value})

        assert response.status_code == 422

    def test_blank_optional_extended_fields_are_stored_as_null(self, client):
        createHolder(
            client,
            nationality="   ",
            birthplace="   ",
            documentExpiry="   ",
        )

        response = getDetails(client)

        assert response.status_code == 200
        assert response.json()["nationality"] is None
        assert response.json()["birthplace"] is None
        assert response.json()["documentExpiry"] is None


class TestExtendedProfileAuthorization:
    def test_details_require_the_correct_holder_pin(self, client):
        createHolder(client)

        response = getDetails(client, pin="999999")

        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid PIN"

    def test_details_require_pin_enrollment(self, client):
        registration = registerIdentity(client)
        assert registration.status_code == 201

        response = getDetails(client)

        assert response.status_code == 409
        assert "No PIN has been set" in response.json()["detail"]

    def test_details_reject_unknown_holder(self, client):
        response = getDetails(client, institutionalId="999999999")

        assert response.status_code == 404
        assert response.json()["detail"] == "User not found"

    def test_details_reject_malformed_institutional_id(self, client):
        response = getDetails(client, institutionalId="ABC-123")

        assert response.status_code == 422
        assert response.json()["detail"] == (
            "Institutional ID must contain exactly 9 digits"
        )

    def test_details_reject_inactive_holder(self, client, mongoDatabase):
        createHolder(client)
        mongoDatabase.users.update_one(
            {"institutional_id": HOLDER_ID},
            {"$set": {"is_active": False}},
        )

        response = getDetails(client)

        assert response.status_code == 404
        assert response.json()["detail"] == "User account is not active"

    def test_details_return_not_found_when_badge_is_missing(
        self,
        client,
        mongoDatabase,
    ):
        registration = createHolder(client)
        mongoDatabase.badges.delete_many(
            {"user_id": registration["user"]["id"]},
        )

        response = getDetails(client)

        assert response.status_code == 404
        assert response.json()["detail"] == "Badge profile was not found"


def test_document_expiry_accepts_iso_leap_day(client):
    futureLeapYear = next(
        year
        for year in range(date.today().year + 1, date.today().year + 9)
        if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    )
    createHolder(client, documentExpiry=f"{futureLeapYear}-02-29")

    response = getDetails(client)

    assert response.status_code == 200
    assert response.json()["documentExpiry"] == f"{futureLeapYear}-02-29"
