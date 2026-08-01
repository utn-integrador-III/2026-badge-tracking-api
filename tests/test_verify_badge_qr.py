import base64
import json
from datetime import datetime, timedelta, timezone


PHOTO_URL = "https://example.com/profile-photo.png"


def registerUser(client, institutionalId: str = "123456789") -> object:
    return client.post(
        "/users/institutional-identities",
        json={
            "fullName": "Kevin Picado",
            "email": f"{institutionalId}@utn.ac.cr",
            "role": "student",
            "institutionalId": institutionalId,
            "photoUrl": PHOTO_URL,
        },
    )


def setPin(client, institutionalId: str = "123456789", pin: str = "281992") -> object:
    return client.post(
        f"/users/{institutionalId}/pin",
        json={"pin": pin, "pinConfirm": pin},
    )


def registerUserWithPin(
    client,
    institutionalId: str = "123456789",
    pin: str = "281992",
) -> None:
    registerUser(client, institutionalId=institutionalId)
    setPin(client, institutionalId=institutionalId, pin=pin)


def generateVerificationQr(
    client,
    institutionalId: str = "123456789",
    pin: str = "281992",
    disclose: list[str] | None = None,
    expiresInSeconds: int | None = None,
) -> object:
    payload: dict = {"pin": pin}
    if disclose is not None:
        payload["disclose"] = disclose
    if expiresInSeconds is not None:
        payload["expiresInSeconds"] = expiresInSeconds

    return client.post(f"/users/{institutionalId}/verification-qr", json=payload)


def issueToken(client, **kwargs) -> str:
    return generateVerificationQr(client, **kwargs).json()["token"]


def scanToken(client, scannedValue: str) -> object:
    return client.post("/verifications/badge", json={"scannedValue": scannedValue})


def decodePayload(token: str) -> dict:
    payloadSegment = token.split(".")[0]
    padding = "=" * (-len(payloadSegment) % 4)
    return json.loads(base64.urlsafe_b64decode(payloadSegment + padding))


def encodePayload(payload: dict) -> str:
    serialized = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(serialized).decode().rstrip("=")


class TestGenerateVerificationQr:
    def test_generate_qr_successfully(self, client):
        registerUserWithPin(client)

        response = generateVerificationQr(client)

        assert response.status_code == 201
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["referrer-policy"] == "no-referrer"
        body = response.json()
        assert body["disclosedAttributes"] == ["fullName", "photoUrl", "role"]
        assert body["expiresInSeconds"] == 120
        assert body["qrCodeImage"].startswith("data:image/png;base64,")
        assert body["verificationUrl"].endswith(
            f"/verifications/badge/{body['token']}"
        )

    def test_token_carries_a_payload_and_a_signature(self, client):
        registerUserWithPin(client)

        token = issueToken(client)

        payloadSegment, separator, signatureSegment = token.partition(".")
        assert separator == "."
        assert payloadSegment and signatureSegment

    def test_generate_qr_honours_requested_attributes(self, client):
        registerUserWithPin(client)

        response = generateVerificationQr(
            client,
            disclose=["role", "badgeCode"],
        )

        assert response.status_code == 201
        assert response.json()["disclosedAttributes"] == ["role", "badgeCode"]

    def test_generate_qr_rejects_unknown_attribute(self, client):
        registerUserWithPin(client)

        response = generateVerificationQr(client, disclose=["email"])

        assert response.status_code == 422

    def test_generate_qr_rejects_empty_attribute_list(self, client):
        registerUserWithPin(client)

        response = generateVerificationQr(client, disclose=[])

        assert response.status_code == 422

    def test_generate_qr_rejects_repeated_attributes(self, client):
        registerUserWithPin(client)

        response = generateVerificationQr(client, disclose=["role", "role"])

        assert response.status_code == 422

    def test_generate_qr_requires_correct_pin(self, client):
        registerUserWithPin(client)

        response = generateVerificationQr(client, pin="999999")

        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid PIN"

    def test_generate_qr_requires_signing_key(self, client, monkeypatch):
        registerUserWithPin(client)
        monkeypatch.delenv("BADGE_TRACKING_SIGNING_KEY")

        response = generateVerificationQr(client)

        assert response.status_code == 503
        assert response.json()["detail"] == (
            "BADGE_TRACKING_SIGNING_KEY must be configured"
        )

    def test_generate_qr_requires_pin_to_be_set_first(self, client):
        registerUser(client)

        response = generateVerificationQr(client)

        assert response.status_code == 409
        assert "No PIN has been set" in response.json()["detail"]

    def test_generate_qr_rejects_unknown_user(self, client):
        response = generateVerificationQr(client, institutionalId="999999999")

        assert response.status_code == 404
        assert response.json()["detail"] == "User not found"

    def test_generate_qr_rejects_invalid_institutional_id_format(self, client):
        response = generateVerificationQr(client, institutionalId="ABC-123")

        assert response.status_code == 422
        assert "9 digits" in response.json()["detail"]

    def test_generate_qr_rejects_revoked_badge(self, client, mongoDatabase):
        registerUserWithPin(client)
        mongoDatabase.badges.update_one(
            {"badge_code": {"$exists": True}},
            {"$set": {"status": "revoked"}},
        )

        response = generateVerificationQr(client)

        assert response.status_code == 409
        assert "cannot be shared" in response.json()["detail"]

    def test_generate_qr_rejects_expired_badge(self, client, mongoDatabase):
        registerUserWithPin(client)
        now = datetime.now(timezone.utc)
        mongoDatabase.badges.update_one(
            {"badge_code": {"$exists": True}},
            {
                "$set": {
                    "valid_from": (now - timedelta(days=2)).isoformat(),
                    "valid_until": (now - timedelta(days=1)).isoformat(),
                }
            },
        )

        response = generateVerificationQr(client)

        assert response.status_code == 409
        assert "badge_expired" in response.json()["detail"]

    def test_disclosed_role_comes_from_the_issued_badge(
        self,
        client,
        mongoDatabase,
    ):
        registerUserWithPin(client)
        mongoDatabase.badges.update_one(
            {"badge_code": {"$exists": True}},
            {"$set": {"role_type": "staff"}},
        )

        response = scanToken(
            client,
            issueToken(client, disclose=["role"]),
        )

        assert response.json()["result"] == "pass"
        assert response.json()["disclosedAttributes"] == {"role": "staff"}

    def test_legacy_badge_without_role_type_uses_institutional_role(
        self,
        client,
        mongoDatabase,
    ):
        registerUserWithPin(client)
        mongoDatabase.badges.update_one(
            {"badge_code": {"$exists": True}},
            {"$unset": {"role_type": ""}},
        )

        response = scanToken(
            client,
            issueToken(client, disclose=["role"]),
        )

        assert response.json()["result"] == "pass"
        assert response.json()["disclosedAttributes"] == {"role": "student"}

    def test_generate_qr_rejects_invalid_badge_role(self, client, mongoDatabase):
        registerUserWithPin(client)
        mongoDatabase.badges.update_one(
            {"badge_code": {"$exists": True}},
            {"$set": {"role_type": "visitor"}},
        )

        response = generateVerificationQr(client, disclose=["role"])

        assert response.status_code == 409
        assert response.json()["detail"] == "Badge role type is invalid"

    def test_generate_qr_rejects_lifetime_outside_allowed_range(self, client):
        registerUserWithPin(client)

        tooShort = generateVerificationQr(client, expiresInSeconds=5)
        tooLong = generateVerificationQr(client, expiresInSeconds=86400)

        assert tooShort.status_code == 422
        assert tooLong.status_code == 422

    def test_generated_qr_expires_after_the_requested_lifetime(self, client):
        registerUserWithPin(client)

        body = generateVerificationQr(client, expiresInSeconds=300).json()

        issuedAt = datetime.fromisoformat(body["issuedAt"])
        expiresAt = datetime.fromisoformat(body["expiresAt"])
        assert expiresAt - issuedAt == timedelta(seconds=300)


class TestScanBadgeVerification:
    def test_scan_returns_pass_with_disclosed_attributes(self, client):
        registerUserWithPin(client)
        token = issueToken(client)

        response = scanToken(client, token)

        assert response.status_code == 200
        body = response.json()
        assert body["result"] == "pass"
        assert body["signatureValid"] is True
        assert body["reasons"] == []
        assert body["badgeStatus"] == "issued"
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert body["disclosedAttributes"] == {
            "fullName": "Kevin Picado",
            "photoUrl": PHOTO_URL,
            "role": "student",
        }

    def test_scan_returns_only_the_attributes_the_holder_disclosed(self, client):
        registerUserWithPin(client)
        token = issueToken(client, disclose=["role"])

        response = scanToken(client, token)

        body = response.json()
        assert body["disclosedAttributes"] == {"role": "student"}
        assert "Kevin Picado" not in response.text
        assert "123456789" not in response.text

    def test_scan_accepts_the_full_verification_url(self, client):
        registerUserWithPin(client)
        qr = generateVerificationQr(client).json()

        response = scanToken(client, qr["verificationUrl"])

        assert response.status_code == 200
        assert response.json()["result"] == "pass"

    def test_scan_accepts_surrounding_whitespace(self, client):
        registerUserWithPin(client)
        token = issueToken(client)

        response = scanToken(client, f"  {token}\n")

        assert response.json()["result"] == "pass"

    def test_scanning_the_url_directly_returns_the_same_verdict(self, client):
        registerUserWithPin(client)
        qr = generateVerificationQr(client).json()

        getResponse = client.get(f"/verifications/badge/{qr['token']}")
        postResponse = scanToken(client, qr["token"])

        assert getResponse.status_code == 200
        assert getResponse.headers["cache-control"] == "no-store"
        assert getResponse.headers["referrer-policy"] == "no-referrer"
        assert getResponse.json()["result"] == postResponse.json()["result"]
        assert (
            getResponse.json()["disclosedAttributes"]
            == postResponse.json()["disclosedAttributes"]
        )

    def test_tampered_attributes_fail_the_signature_check(self, client):
        registerUserWithPin(client)
        token = issueToken(client)

        payload = decodePayload(token)
        payload["att"]["fullName"] = "Someone Else"
        forgedToken = f"{encodePayload(payload)}.{token.split('.')[1]}"

        response = scanToken(client, forgedToken)

        body = response.json()
        assert body["result"] == "fail"
        assert body["signatureValid"] is False
        assert body["reasons"] == ["invalid_signature"]

    def test_failed_signature_never_returns_attributes(self, client):
        registerUserWithPin(client)
        token = issueToken(client)

        payload = decodePayload(token)
        payload["att"]["role"] = "staff"
        forgedToken = f"{encodePayload(payload)}.{token.split('.')[1]}"

        response = scanToken(client, forgedToken)

        assert response.json()["disclosedAttributes"] == {}
        assert "staff" not in response.text

    def test_tampered_signature_fails(self, client):
        registerUserWithPin(client)
        token = issueToken(client)

        payloadSegment, _, signatureSegment = token.partition(".")
        forgedSignature = ("A" if signatureSegment[0] != "A" else "B") + (
            signatureSegment[1:]
        )

        response = scanToken(client, f"{payloadSegment}.{forgedSignature}")

        assert response.json()["reasons"] == ["invalid_signature"]

    def test_token_signed_with_another_key_fails(self, client, monkeypatch):
        registerUserWithPin(client)
        token = issueToken(client)

        monkeypatch.setenv(
            "BADGE_TRACKING_SIGNING_KEY",
            "a-different-signing-key-with-at-least-32-bytes",
        )
        response = scanToken(client, token)

        assert response.json()["result"] == "fail"
        assert response.json()["reasons"] == ["invalid_signature"]

    def test_scan_requires_signing_key(self, client, monkeypatch):
        registerUserWithPin(client)
        token = issueToken(client)
        monkeypatch.delenv("BADGE_TRACKING_SIGNING_KEY")

        response = scanToken(client, token)

        assert response.status_code == 503
        assert response.json()["detail"] == (
            "BADGE_TRACKING_SIGNING_KEY must be configured"
        )

    def test_malformed_scan_value_fails_without_error(self, client):
        response = scanToken(client, "not-a-badge-qr")

        assert response.status_code == 200
        body = response.json()
        assert body["result"] == "fail"
        assert body["signatureValid"] is False
        assert body["reasons"] == ["malformed_token"]

    def test_expired_token_fails(self, client):
        registerUserWithPin(client)
        token = issueToken(client, expiresInSeconds=30)

        now = datetime.now(timezone.utc)
        payload = decodePayload(token)
        payload["iat"] = (now - timedelta(minutes=2)).isoformat()
        payload["exp"] = (now - timedelta(seconds=1)).isoformat()

        # Re-sign through the same helper the API uses, so only expiry differs.
        from utils.signing import signPayload

        response = scanToken(client, signPayload(payload))

        body = response.json()
        assert body["result"] == "fail"
        assert body["signatureValid"] is True
        assert body["reasons"] == ["expired"]
        assert body["disclosedAttributes"]["fullName"] == "Kevin Picado"

    def test_future_credential_returns_fail_with_signed_attributes(self, client):
        from utils.signing import signPayload

        registerUserWithPin(client)
        payload = decodePayload(issueToken(client))
        now = datetime.now(timezone.utc)
        payload["iat"] = (now + timedelta(minutes=1)).isoformat()
        payload["exp"] = (now + timedelta(minutes=3)).isoformat()

        response = scanToken(client, signPayload(payload))

        body = response.json()
        assert body["result"] == "fail"
        assert body["signatureValid"] is True
        assert body["reasons"] == ["credential_not_yet_valid"]
        assert body["disclosedAttributes"]["role"] == "student"

    def test_signed_credential_with_invalid_expiry_fails_cleanly(self, client):
        from utils.signing import signPayload

        registerUserWithPin(client)
        payload = decodePayload(issueToken(client))
        payload["exp"] = "not-a-timestamp"

        response = scanToken(client, signPayload(payload))

        body = response.json()
        assert response.status_code == 200
        assert body["result"] == "fail"
        assert body["signatureValid"] is True
        assert body["reasons"] == ["malformed_token"]
        assert body["disclosedAttributes"] == {}

    def test_signed_credential_with_naive_timestamp_fails_cleanly(self, client):
        from utils.signing import signPayload

        registerUserWithPin(client)
        payload = decodePayload(issueToken(client))
        payload["exp"] = datetime.now().isoformat()

        response = scanToken(client, signPayload(payload))

        assert response.status_code == 200
        assert response.json()["reasons"] == ["malformed_token"]

    def test_signed_credential_with_non_positive_lifetime_fails_cleanly(
        self,
        client,
    ):
        from utils.signing import signPayload

        registerUserWithPin(client)
        payload = decodePayload(issueToken(client))
        payload["exp"] = payload["iat"]

        response = scanToken(client, signPayload(payload))

        assert response.status_code == 200
        assert response.json()["result"] == "fail"
        assert response.json()["reasons"] == ["malformed_token"]

    def test_signed_credential_cannot_exceed_maximum_lifetime(self, client):
        from utils.signing import signPayload

        registerUserWithPin(client)
        payload = decodePayload(issueToken(client))
        issuedAt = datetime.fromisoformat(payload["iat"])
        payload["exp"] = (issuedAt + timedelta(seconds=901)).isoformat()

        response = scanToken(client, signPayload(payload))

        assert response.status_code == 200
        assert response.json()["result"] == "fail"
        assert response.json()["reasons"] == ["malformed_token"]
        assert response.json()["disclosedAttributes"] == {}

    def test_signed_credential_without_badge_id_fails_cleanly(self, client):
        from utils.signing import signPayload

        registerUserWithPin(client)
        payload = decodePayload(issueToken(client))
        payload.pop("bid")

        response = scanToken(client, signPayload(payload))

        assert response.status_code == 200
        assert response.json()["result"] == "fail"
        assert response.json()["reasons"] == ["malformed_token"]

    def test_signed_non_object_payload_fails_cleanly(self, client):
        from utils.signing import signPayload

        response = scanToken(client, signPayload(["not", "an", "object"]))

        body = response.json()
        assert response.status_code == 200
        assert body["result"] == "fail"
        assert body["signatureValid"] is True
        assert body["reasons"] == ["malformed_token"]

    def test_signed_credential_with_unknown_attribute_fails_cleanly(self, client):
        from utils.signing import signPayload

        registerUserWithPin(client)
        payload = decodePayload(issueToken(client))
        payload["att"] = {"email": "kevin@utn.ac.cr"}

        response = scanToken(client, signPayload(payload))

        assert response.status_code == 200
        assert response.json()["result"] == "fail"
        assert response.json()["reasons"] == ["malformed_token"]

    def test_badge_revoked_after_issuing_fails(self, client, mongoDatabase):
        registerUserWithPin(client)
        token = issueToken(client)

        mongoDatabase.badges.update_one(
            {"badge_code": {"$exists": True}},
            {"$set": {"status": "revoked"}},
        )
        response = scanToken(client, token)

        body = response.json()
        assert body["result"] == "fail"
        assert body["reasons"] == ["badge_not_active"]
        assert body["badgeStatus"] == "revoked"
        assert body["disclosedAttributes"]["fullName"] == "Kevin Picado"

    def test_badge_expired_after_qr_generation_fails(
        self,
        client,
        mongoDatabase,
    ):
        registerUserWithPin(client)
        token = issueToken(client)
        now = datetime.now(timezone.utc)
        mongoDatabase.badges.update_one(
            {"badge_code": {"$exists": True}},
            {
                "$set": {
                    "valid_from": (now - timedelta(days=2)).isoformat(),
                    "valid_until": (now - timedelta(seconds=1)).isoformat(),
                }
            },
        )

        response = scanToken(client, token)

        body = response.json()
        assert body["result"] == "fail"
        assert body["reasons"] == ["badge_expired"]
        assert body["badgeStatus"] == "issued"

    def test_badge_not_yet_valid_after_qr_generation_fails(
        self,
        client,
        mongoDatabase,
    ):
        registerUserWithPin(client)
        token = issueToken(client)
        now = datetime.now(timezone.utc)
        mongoDatabase.badges.update_one(
            {"badge_code": {"$exists": True}},
            {
                "$set": {
                    "valid_from": (now + timedelta(minutes=1)).isoformat(),
                    "valid_until": (now + timedelta(days=1)).isoformat(),
                }
            },
        )

        response = scanToken(client, token)

        body = response.json()
        assert body["result"] == "fail"
        assert body["reasons"] == ["badge_not_yet_valid"]

    def test_invalid_badge_validity_fails_cleanly(self, client, mongoDatabase):
        registerUserWithPin(client)
        token = issueToken(client)
        mongoDatabase.badges.update_one(
            {"badge_code": {"$exists": True}},
            {"$set": {"valid_until": "not-a-timestamp"}},
        )

        response = scanToken(client, token)

        body = response.json()
        assert body["result"] == "fail"
        assert body["reasons"] == ["badge_validity_invalid"]

    def test_missing_badge_validity_fails_closed(self, client, mongoDatabase):
        registerUserWithPin(client)
        token = issueToken(client)
        mongoDatabase.badges.update_one(
            {"badge_code": {"$exists": True}},
            {"$unset": {"valid_until": ""}},
        )

        response = scanToken(client, token)

        body = response.json()
        assert body["result"] == "fail"
        assert body["reasons"] == ["badge_validity_invalid"]

    def test_deleted_user_fails(
        self,
        client,
        mongoDatabase,
    ):
        registerUserWithPin(client)
        token = issueToken(client)
        mongoDatabase.users.delete_one({"institutional_id": "123456789"})

        response = scanToken(client, token)

        body = response.json()
        assert body["result"] == "fail"
        assert body["reasons"] == ["user_not_found"]

    def test_deleted_badge_fails(
        self,
        client,
        mongoDatabase,
    ):
        registerUserWithPin(client)
        token = issueToken(client)
        mongoDatabase.badges.delete_one({"badge_code": {"$exists": True}})

        response = scanToken(client, token)

        body = response.json()
        assert body["result"] == "fail"
        assert body["reasons"] == ["badge_not_found"]

    def test_suspended_badge_fails(
        self,
        client,
        mongoDatabase,
    ):
        registerUserWithPin(client)
        token = issueToken(client)
        mongoDatabase.badges.update_one(
            {"badge_code": {"$exists": True}},
            {"$set": {"status": "suspended"}},
        )

        response = scanToken(client, token)

        body = response.json()
        assert body["result"] == "fail"
        assert body["reasons"] == ["badge_not_active"]
        assert body["badgeStatus"] == "suspended"

    def test_missing_badge_status_fails_cleanly(self, client, mongoDatabase):
        registerUserWithPin(client)
        token = issueToken(client)
        mongoDatabase.badges.update_one(
            {"badge_code": {"$exists": True}},
            {"$unset": {"status": ""}},
        )

        response = scanToken(client, token)

        body = response.json()
        assert body["result"] == "fail"
        assert body["reasons"] == ["badge_not_active"]
        assert body["badgeStatus"] is None

    def test_deactivated_user_fails(self, client, mongoDatabase):
        registerUserWithPin(client)
        token = issueToken(client)

        mongoDatabase.users.update_one(
            {"institutional_id": "123456789"},
            {"$set": {"is_active": False}},
        )
        response = scanToken(client, token)

        assert response.json()["result"] == "fail"
        assert response.json()["reasons"] == ["user_inactive"]

    def test_unsupported_credential_version_fails(self, client):
        from utils.signing import signPayload

        registerUserWithPin(client)
        payload = decodePayload(issueToken(client))
        payload["v"] = 99

        response = scanToken(client, signPayload(payload))

        assert response.json()["reasons"] == ["unsupported_credential_version"]

    def test_future_credential_schema_is_reported_as_unsupported(self, client):
        from utils.signing import signPayload

        response = scanToken(
            client,
            signPayload({"v": 2, "futureCredential": "different-schema"}),
        )

        body = response.json()
        assert response.status_code == 200
        assert body["result"] == "fail"
        assert body["signatureValid"] is True
        assert body["reasons"] == ["unsupported_credential_version"]
        assert body["disclosedAttributes"] == {}

    def test_scan_can_be_repeated_before_expiry(self, client):
        registerUserWithPin(client)
        token = issueToken(client)

        firstScan = scanToken(client, token)
        secondScan = scanToken(client, token)

        assert firstScan.json()["result"] == "pass"
        assert secondScan.json()["result"] == "pass"

    def test_each_scan_gets_its_own_verification_id(self, client):
        registerUserWithPin(client)
        token = issueToken(client)

        firstScan = scanToken(client, token).json()
        secondScan = scanToken(client, token).json()

        assert firstScan["verificationId"] != secondScan["verificationId"]

    def test_each_scan_is_recorded_for_audit(self, client, mongoDatabase):
        registerUserWithPin(client)
        token = issueToken(client)

        verificationId = scanToken(client, token).json()["verificationId"]
        scanToken(client, "not-a-badge-qr")

        record = mongoDatabase.badge_verifications.find_one(
            {"verification_id": verificationId}
        )
        assert record["result"] == "pass"
        assert record["reasons"] == []
        assert "token" not in record
        assert "disclosed_attributes" not in record
        assert mongoDatabase.badge_verifications.count_documents({}) == 2

    def test_scan_rejects_empty_value(self, client):
        response = scanToken(client, "")

        assert response.status_code == 422

    def test_one_holder_token_does_not_disclose_another_holder(self, client):
        registerUserWithPin(client, institutionalId="111111111", pin="281992")
        registerUserWithPin(client, institutionalId="222222222", pin="375849")

        token = issueToken(
            client,
            institutionalId="222222222",
            pin="375849",
            disclose=["institutionalId"],
        )
        response = scanToken(client, token)

        assert response.json()["disclosedAttributes"] == {
            "institutionalId": "222222222"
        }
