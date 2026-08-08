import pytest


HOLDER_ID = "123456789"
HOLDER_PIN = "281992"
ADMIN_ID = "900000001"
ADMIN_PIN = "481726"
SIGNATURE_URL = "https://identity.utn.ac.cr/signatures/123456789.png"


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
        "digitalSignatureUrl": SIGNATURE_URL,
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
        digitalSignatureUrl=None,
    )
    assert response.status_code == 201
    assert setPin(client, ADMIN_ID, ADMIN_PIN).status_code == 201


class TestDisplayDigitalSignature:
    def test_holder_views_enrolled_signature_in_credential_details(self, client):
        createHolder(client)

        response = getDetails(client)

        assert response.status_code == 200
        assert response.json()["digitalSignatureUrl"] == SIGNATURE_URL

    def test_signature_is_persisted_with_the_identity(self, client, mongoDatabase):
        createHolder(client)

        user = mongoDatabase.users.find_one({"institutional_id": HOLDER_ID})

        assert user["digital_signature_url"] == SIGNATURE_URL

    def test_signature_is_not_exposed_by_public_or_registration_responses(
        self,
        client,
    ):
        registration = createHolder(client)

        publicProfile = client.get(f"/users/{HOLDER_ID}/badge-profile")

        assert publicProfile.status_code == 200
        assert "digitalSignatureUrl" not in registration["user"]
        assert "digitalSignatureUrl" not in registration["badge"]
        assert "digitalSignatureUrl" not in publicProfile.json()
        assert SIGNATURE_URL not in publicProfile.text

    def test_identity_without_an_enrolled_signature_returns_null(self, client):
        createHolder(client, digitalSignatureUrl=None)

        response = getDetails(client)

        assert response.status_code == 200
        assert response.json()["digitalSignatureUrl"] is None

    def test_blank_signature_url_is_stored_as_null(self, client, mongoDatabase):
        createHolder(client, digitalSignatureUrl="   ")

        response = getDetails(client)
        user = mongoDatabase.users.find_one({"institutional_id": HOLDER_ID})

        assert response.status_code == 200
        assert response.json()["digitalSignatureUrl"] is None
        assert user["digital_signature_url"] is None

    def test_signature_url_is_trimmed(self, client):
        createHolder(client, digitalSignatureUrl=f"  {SIGNATURE_URL}  ")

        response = getDetails(client)

        assert response.status_code == 200
        assert response.json()["digitalSignatureUrl"] == SIGNATURE_URL

    def test_signature_remains_available_after_badge_reissue(self, client):
        createAdmin(client)
        createHolder(client)
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
        assert response.json()["roleType"] == "staff"
        assert response.json()["digitalSignatureUrl"] == SIGNATURE_URL

    def test_wrong_pin_never_returns_the_signature_url(self, client):
        createHolder(client)

        response = getDetails(client, pin="999999")

        assert response.status_code == 401
        assert SIGNATURE_URL not in response.text


class TestDigitalSignatureUrlValidation:
    @pytest.mark.parametrize(
        "signatureUrl",
        [
            "http://identity.utn.ac.cr/signature.png",
            "javascript:alert(1)",
            "data:image/png;base64,AAAA",
            "file:///tmp/signature.png",
            "/signatures/123456789.png",
            "not-a-url",
            "https://identity.utn.ac.cr/signature image.png",
        ],
    )
    def test_registration_rejects_non_https_signature_urls(
        self,
        client,
        signatureUrl,
    ):
        response = registerIdentity(client, digitalSignatureUrl=signatureUrl)

        assert response.status_code == 422

    def test_registration_rejects_url_credentials(self, client):
        response = registerIdentity(
            client,
            digitalSignatureUrl=(
                "https://username:password@identity.utn.ac.cr/signature.png"
            ),
        )

        assert response.status_code == 422

    def test_registration_rejects_signature_url_over_2048_characters(self, client):
        prefix = "https://identity.utn.ac.cr/signatures/"
        response = registerIdentity(
            client,
            digitalSignatureUrl=prefix + ("a" * (2049 - len(prefix))),
        )

        assert response.status_code == 422

    def test_registration_accepts_signature_url_at_2048_characters(self, client):
        prefix = "https://identity.utn.ac.cr/signatures/"
        signatureUrl = prefix + ("a" * (2048 - len(prefix)))
        createHolder(client, digitalSignatureUrl=signatureUrl)

        response = getDetails(client)

        assert response.status_code == 200
        assert response.json()["digitalSignatureUrl"] == signatureUrl

    def test_registration_accepts_https_query_and_fragment(self, client):
        signatureUrl = f"{SIGNATURE_URL}?version=2#preview"
        createHolder(client, digitalSignatureUrl=signatureUrl)

        response = getDetails(client)

        assert response.status_code == 200
        assert response.json()["digitalSignatureUrl"] == signatureUrl
