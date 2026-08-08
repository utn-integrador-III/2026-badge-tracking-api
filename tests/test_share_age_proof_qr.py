from datetime import date, datetime, timedelta, timezone


ADULT_BIRTH_DATE = "1992-08-28"
MINOR_BIRTH_DATE = date(datetime.now(timezone.utc).year - 15, 1, 1).isoformat()


def registerUser(
    client,
    institutionalId: str = "123456789",
    birthDate: str | None = ADULT_BIRTH_DATE,
) -> object:
    payload = {
        "fullName": "Kevin Picado",
        "email": f"{institutionalId}@utn.ac.cr",
        "role": "student",
        "institutionalId": institutionalId,
    }
    if birthDate is not None:
        payload["birthDate"] = birthDate

    return client.post("/users/institutional-identities", json=payload)


def setPin(client, institutionalId: str = "123456789", pin: str = "281992") -> object:
    return client.post(
        f"/users/{institutionalId}/pin",
        json={"pin": pin, "pinConfirm": pin},
    )


def generateAgeProofQr(
    client,
    institutionalId: str = "123456789",
    pin: str = "281992",
    minimumAge: int | None = None,
    expiresInSeconds: int | None = None,
) -> object:
    payload: dict = {"pin": pin}
    if minimumAge is not None:
        payload["minimumAge"] = minimumAge
    if expiresInSeconds is not None:
        payload["expiresInSeconds"] = expiresInSeconds

    return client.post(f"/users/{institutionalId}/age-proof-qr", json=payload)


def registerUserWithPin(
    client,
    institutionalId: str = "123456789",
    birthDate: str | None = ADULT_BIRTH_DATE,
    pin: str = "281992",
) -> None:
    registerUser(client, institutionalId=institutionalId, birthDate=birthDate)
    setPin(client, institutionalId=institutionalId, pin=pin)


class TestGenerateAgeProofQr:
    def test_generate_qr_successfully(self, client):
        registerUserWithPin(client)

        response = generateAgeProofQr(client)

        assert response.status_code == 201
        body = response.json()
        assert body["minimumAge"] == 18
        assert body["meetsMinimumAge"] is True
        assert body["expiresInSeconds"] == 120
        assert body["qrCodeImage"].startswith("data:image/png;base64,")
        assert body["token"] in body["verificationUrl"]
        assert body["verificationUrl"].endswith(
            f"/verifications/age-proof/{body['token']}"
        )

    def test_generated_qr_expires_after_the_requested_lifetime(self, client):
        registerUserWithPin(client)

        response = generateAgeProofQr(client, expiresInSeconds=300)

        body = response.json()
        issuedAt = datetime.fromisoformat(body["issuedAt"])
        expiresAt = datetime.fromisoformat(body["expiresAt"])

        assert expiresAt - issuedAt == timedelta(seconds=300)

    def test_generate_qr_uses_custom_minimum_age(self, client):
        registerUserWithPin(client)

        response = generateAgeProofQr(client, minimumAge=65)

        assert response.status_code == 201
        body = response.json()
        assert body["minimumAge"] == 65
        assert body["meetsMinimumAge"] is False

    def test_generate_qr_flags_holder_below_minimum_age(self, client):
        registerUserWithPin(client, birthDate=MINOR_BIRTH_DATE)

        response = generateAgeProofQr(client)

        assert response.status_code == 201
        assert response.json()["meetsMinimumAge"] is False

    def test_generate_qr_requires_correct_pin(self, client):
        registerUserWithPin(client)

        response = generateAgeProofQr(client, pin="999999")

        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid PIN"

    def test_generate_qr_requires_pin_to_be_set_first(self, client):
        registerUser(client)

        response = generateAgeProofQr(client)

        assert response.status_code == 409
        assert "No PIN has been set" in response.json()["detail"]

    def test_generate_qr_requires_registered_birth_date(self, client):
        registerUserWithPin(client, birthDate=None)

        response = generateAgeProofQr(client)

        assert response.status_code == 409
        assert "date of birth" in response.json()["detail"]

    def test_generate_qr_rejects_unknown_user(self, client):
        response = generateAgeProofQr(client, institutionalId="999999999")

        assert response.status_code == 404
        assert response.json()["detail"] == "User not found"

    def test_generate_qr_rejects_invalid_institutional_id_format(self, client):
        response = generateAgeProofQr(client, institutionalId="ABC-123")

        assert response.status_code == 422
        assert "9 digits" in response.json()["detail"]

    def test_generate_qr_rejects_revoked_badge(self, client, mongoDatabase):
        registerUserWithPin(client)
        mongoDatabase.badges.update_one(
            {"badge_code": {"$exists": True}},
            {"$set": {"status": "revoked"}},
        )

        response = generateAgeProofQr(client)

        assert response.status_code == 409
        assert "cannot be shared" in response.json()["detail"]

    def test_generate_qr_rejects_lifetime_outside_allowed_range(self, client):
        registerUserWithPin(client)

        tooShort = generateAgeProofQr(client, expiresInSeconds=5)
        tooLong = generateAgeProofQr(client, expiresInSeconds=86400)

        assert tooShort.status_code == 422
        assert tooLong.status_code == 422

    def test_each_generated_qr_uses_a_new_token(self, client):
        registerUserWithPin(client)

        firstToken = generateAgeProofQr(client).json()["token"]
        secondToken = generateAgeProofQr(client).json()["token"]

        assert firstToken != secondToken

    def test_token_is_not_stored_in_plain_text(self, client, mongoDatabase):
        registerUserWithPin(client)

        token = generateAgeProofQr(client).json()["token"]
        storedToken = mongoDatabase.age_proof_tokens.find_one({})

        assert mongoDatabase.age_proof_tokens.find_one({"token": token}) is None
        assert storedToken["token_hash"] != token


class TestVerifyAgeProof:
    def test_verifying_party_sees_only_age_proof(self, client):
        registerUserWithPin(client)
        token = generateAgeProofQr(client).json()["token"]

        response = client.get(f"/verifications/age-proof/{token}")

        assert response.status_code == 200
        body = response.json()
        assert body["valid"] is True
        assert body["minimumAge"] == 18
        assert body["meetsMinimumAge"] is True
        assert body["badgeStatus"] == "issued"
        assert set(body) == {
            "valid",
            "minimumAge",
            "meetsMinimumAge",
            "role",
            "badgeStatus",
            "issuedAt",
            "expiresAt",
            "verifiedAt",
        }

    def test_verification_never_exposes_identity_data(self, client):
        registerUserWithPin(client)
        token = generateAgeProofQr(client).json()["token"]

        response = client.get(f"/verifications/age-proof/{token}")

        serializedBody = response.text
        assert "Kevin Picado" not in serializedBody
        assert "123456789" not in serializedBody
        assert ADULT_BIRTH_DATE not in serializedBody
        assert "BADGE-" not in serializedBody
        assert "utn.ac.cr" not in serializedBody

    def test_verification_does_not_reveal_exact_age(self, client):
        registerUserWithPin(client)
        token = generateAgeProofQr(client).json()["token"]

        body = client.get(f"/verifications/age-proof/{token}").json()

        assert "age" not in body
        assert "birthDate" not in body

    def test_verification_rejects_unknown_token(self, client):
        response = client.get("/verifications/age-proof/not-a-real-token")

        assert response.status_code == 404
        assert response.json()["detail"] == "Age proof QR code was not found"

    def test_verification_rejects_expired_token(self, client, mongoDatabase):
        registerUserWithPin(client)
        token = generateAgeProofQr(client).json()["token"]
        expiredAt = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        mongoDatabase.age_proof_tokens.update_one(
            {"token_hash": {"$exists": True}},
            {"$set": {"expires_at": expiredAt}},
        )

        response = client.get(f"/verifications/age-proof/{token}")

        assert response.status_code == 410
        assert response.json()["detail"] == "Age proof QR code has expired"

    def test_token_can_be_verified_more_than_once_before_expiry(self, client):
        registerUserWithPin(client)
        token = generateAgeProofQr(client).json()["token"]

        firstResponse = client.get(f"/verifications/age-proof/{token}")
        secondResponse = client.get(f"/verifications/age-proof/{token}")

        assert firstResponse.status_code == 200
        assert secondResponse.status_code == 200

    def test_token_of_one_holder_does_not_verify_another(self, client):
        registerUserWithPin(client, institutionalId="111111111", pin="281992")
        registerUserWithPin(
            client,
            institutionalId="222222222",
            birthDate=MINOR_BIRTH_DATE,
            pin="375849",
        )

        minorToken = generateAgeProofQr(
            client,
            institutionalId="222222222",
            pin="375849",
        ).json()["token"]

        body = client.get(f"/verifications/age-proof/{minorToken}").json()

        assert body["meetsMinimumAge"] is False


class TestBirthDateRegistration:
    def test_birth_date_is_optional(self, client):
        response = registerUser(client, birthDate=None)

        assert response.status_code == 201

    def test_birth_date_is_not_exposed_in_badge_profile(self, client):
        registerUser(client)

        response = client.get("/users/123456789/badge-profile")

        assert response.status_code == 200
        assert "birthDate" not in response.json()

    def test_registration_rejects_malformed_birth_date(self, client):
        response = registerUser(client, birthDate="28-08-1992")

        assert response.status_code == 422

    def test_registration_rejects_future_birth_date(self, client):
        futureDate = (datetime.now(timezone.utc) + timedelta(days=1)).date()

        response = registerUser(client, birthDate=futureDate.isoformat())

        assert response.status_code == 422

    def test_registration_rejects_unrealistic_birth_date(self, client):
        response = registerUser(client, birthDate="1850-01-01")

        assert response.status_code == 422
