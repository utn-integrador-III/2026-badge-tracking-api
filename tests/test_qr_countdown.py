import base64
import json
from datetime import datetime, timedelta, timezone

import pytest


HOLDER_ID = "123456789"
HOLDER_PIN = "281992"
BIRTH_DATE = "1992-08-28"
SIGNING_KEY = "test-only-signing-key-with-at-least-32-bytes"


def registerHolder(client, institutionalId: str = HOLDER_ID) -> None:
    registration = client.post(
        "/users/institutional-identities",
        json={
            "fullName": "Kevin Picado",
            "email": f"{institutionalId}@utn.ac.cr",
            "role": "student",
            "institutionalId": institutionalId,
            "birthDate": BIRTH_DATE,
        },
    )
    assert registration.status_code == 201

    pinResponse = client.post(
        f"/users/{institutionalId}/pin",
        json={"pin": HOLDER_PIN, "pinConfirm": HOLDER_PIN},
    )
    assert pinResponse.status_code == 201


def generateBadgeQr(client, expiresInSeconds: int | None = None):
    payload: dict = {"pin": HOLDER_PIN}
    if expiresInSeconds is not None:
        payload["expiresInSeconds"] = expiresInSeconds

    return client.post(f"/users/{HOLDER_ID}/verification-qr", json=payload)


def generateAgeProofQr(client, expiresInSeconds: int | None = None):
    payload: dict = {"pin": HOLDER_PIN}
    if expiresInSeconds is not None:
        payload["expiresInSeconds"] = expiresInSeconds

    return client.post(f"/users/{HOLDER_ID}/age-proof-qr", json=payload)


def readCountdown(client, token: str):
    return client.get(f"/verifications/countdown/{token}")


def scanCountdown(client, scannedValue: str):
    return client.post(
        "/verifications/countdown",
        json={"scannedValue": scannedValue},
    )


def reSignWithExpiry(token: str, expiresAt: str) -> str:
    """Re-mint a badge token so its window can be moved in a test."""
    from utils.signing import signPayload

    payloadSegment = token.split(".")[0]
    padding = "=" * (-len(payloadSegment) % 4)
    payload = json.loads(base64.urlsafe_b64decode(payloadSegment + padding))
    payload["exp"] = expiresAt

    return signPayload(payload)


@pytest.fixture()
def holder(client, monkeypatch):
    monkeypatch.setenv("BADGE_TRACKING_SIGNING_KEY", SIGNING_KEY)
    registerHolder(client)
    return client


class TestConfigurableLifetime:
    def test_a_qr_lasts_sixty_seconds_by_default(self, holder):
        badgeQr = generateBadgeQr(holder).json()
        ageProofQr = generateAgeProofQr(holder).json()

        for qrCode in (badgeQr, ageProofQr):
            assert qrCode["expiresInSeconds"] == 60
            issuedAt = datetime.fromisoformat(qrCode["issuedAt"])
            expiresAt = datetime.fromisoformat(qrCode["expiresAt"])
            assert expiresAt - issuedAt == timedelta(seconds=60)

    def test_the_deployment_can_configure_the_default(self, holder, monkeypatch):
        monkeypatch.setenv("BADGE_TRACKING_QR_LIFETIME_SECONDS", "45")

        badgeQr = generateBadgeQr(holder).json()
        ageProofQr = generateAgeProofQr(holder).json()

        assert badgeQr["expiresInSeconds"] == 45
        assert ageProofQr["expiresInSeconds"] == 45
        assert badgeQr["remainingSeconds"] == 45

    @pytest.mark.parametrize(
        "configuredLifetime",
        ["", "   ", "not-a-number", "0", "29", "901", "-60", "60.5"],
    )
    def test_an_unusable_configuration_falls_back_to_the_default(
        self,
        holder,
        monkeypatch,
        configuredLifetime,
    ):
        monkeypatch.setenv(
            "BADGE_TRACKING_QR_LIFETIME_SECONDS",
            configuredLifetime,
        )

        response = generateBadgeQr(holder)

        assert response.status_code == 201
        assert response.json()["expiresInSeconds"] == 60

    @pytest.mark.parametrize("requestedLifetime", [30, 300, 900])
    def test_a_client_may_still_choose_its_own_lifetime(
        self,
        holder,
        monkeypatch,
        requestedLifetime,
    ):
        monkeypatch.setenv("BADGE_TRACKING_QR_LIFETIME_SECONDS", "45")

        response = generateBadgeQr(holder, expiresInSeconds=requestedLifetime)

        assert response.status_code == 201
        assert response.json()["expiresInSeconds"] == requestedLifetime

    @pytest.mark.parametrize("requestedLifetime", [5, 29, 901, 86400])
    def test_a_lifetime_outside_the_bounds_is_rejected(
        self,
        holder,
        requestedLifetime,
    ):
        assert generateBadgeQr(
            holder,
            expiresInSeconds=requestedLifetime,
        ).status_code == 422
        assert generateAgeProofQr(
            holder,
            expiresInSeconds=requestedLifetime,
        ).status_code == 422


class TestHolderSeesTheCountdown:
    def test_a_fresh_qr_starts_its_countdown_at_the_full_lifetime(self, holder):
        response = generateBadgeQr(holder, expiresInSeconds=120)

        assert response.status_code == 201
        body = response.json()
        assert body["remainingSeconds"] == 120
        assert body["serverTime"] == body["issuedAt"]

    def test_the_age_proof_qr_reports_the_same_countdown(self, holder):
        response = generateAgeProofQr(holder, expiresInSeconds=90)

        assert response.status_code == 201
        body = response.json()
        assert body["remainingSeconds"] == 90
        assert body["serverTime"] == body["issuedAt"]


class TestCountdownEndpoint:
    def test_the_countdown_reports_a_badge_qr_window(self, holder):
        qrCode = generateBadgeQr(holder, expiresInSeconds=120).json()

        response = readCountdown(holder, qrCode["token"])

        assert response.status_code == 200
        body = response.json()
        assert body["tokenType"] == "badge_verification"
        assert body["issuedAt"] == qrCode["issuedAt"]
        assert body["expiresAt"] == qrCode["expiresAt"]
        assert body["totalSeconds"] == 120
        assert 0 < body["remainingSeconds"] <= 120
        assert body["expired"] is False
        assert datetime.fromisoformat(body["serverTime"]).tzinfo is not None

    def test_the_countdown_reports_an_age_proof_qr_window(self, holder):
        qrCode = generateAgeProofQr(holder, expiresInSeconds=90).json()

        response = readCountdown(holder, qrCode["token"])

        assert response.status_code == 200
        body = response.json()
        assert body["tokenType"] == "age_proof"
        assert body["totalSeconds"] == 90
        assert 0 < body["remainingSeconds"] <= 90
        assert body["expired"] is False

    def test_the_countdown_accepts_the_scanned_url(self, holder):
        badgeQr = generateBadgeQr(holder).json()
        ageProofQr = generateAgeProofQr(holder).json()

        badgeCountdown = scanCountdown(holder, badgeQr["verificationUrl"])
        ageProofCountdown = scanCountdown(holder, ageProofQr["verificationUrl"])

        assert badgeCountdown.status_code == 200
        assert badgeCountdown.json()["tokenType"] == "badge_verification"
        assert ageProofCountdown.status_code == 200
        assert ageProofCountdown.json()["tokenType"] == "age_proof"

    def test_the_countdown_ignores_query_and_fragment_noise(self, holder):
        qrCode = generateBadgeQr(holder).json()

        response = scanCountdown(
            holder,
            f"  {qrCode['verificationUrl']}?utm=poster#scan  ",
        )

        assert response.status_code == 200
        assert response.json()["expiresAt"] == qrCode["expiresAt"]

    def test_the_countdown_runs_down_to_zero(self, holder):
        qrCode = generateBadgeQr(holder).json()
        expiredAt = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()

        response = readCountdown(holder, reSignWithExpiry(qrCode["token"], expiredAt))

        assert response.status_code == 200
        body = response.json()
        assert body["remainingSeconds"] == 0
        assert body["expired"] is True

    def test_an_expired_age_proof_still_reports_its_countdown(
        self,
        holder,
        mongoDatabase,
    ):
        qrCode = generateAgeProofQr(holder).json()
        expiredAt = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        mongoDatabase.age_proof_tokens.update_one(
            {},
            {"$set": {"expires_at": expiredAt}},
        )

        response = readCountdown(holder, qrCode["token"])

        assert response.status_code == 200
        assert response.json()["remainingSeconds"] == 0
        assert response.json()["expired"] is True

    def test_the_countdown_is_never_cached(self, holder):
        qrCode = generateBadgeQr(holder).json()

        response = readCountdown(holder, qrCode["token"])

        assert response.headers["Cache-Control"] == "no-store"

    @pytest.mark.parametrize(
        "token",
        [
            "not-a-token",
            "unknown.signature",
            "a" * 43,
        ],
    )
    def test_an_unreadable_token_is_not_found(self, holder, token):
        assert readCountdown(holder, token).status_code == 404

    def test_a_forged_signature_is_not_found(self, holder):
        qrCode = generateBadgeQr(holder).json()
        payloadSegment = qrCode["token"].split(".")[0]

        response = readCountdown(holder, f"{payloadSegment}.forged-signature")

        assert response.status_code == 404

    def test_the_countdown_never_discloses_the_credential(self, holder):
        qrCode = generateBadgeQr(holder).json()

        response = readCountdown(holder, qrCode["token"])

        assert response.status_code == 200
        assert "Kevin Picado" not in response.text
        assert HOLDER_ID not in response.text
        assert "disclosedAttributes" not in response.text

    def test_polling_the_countdown_leaves_no_audit_trail(
        self,
        holder,
        mongoDatabase,
    ):
        qrCode = generateBadgeQr(holder).json()

        for _ in range(5):
            assert readCountdown(holder, qrCode["token"]).status_code == 200

        assert mongoDatabase.badge_verifications.count_documents({}) == 0


class TestVerifierSeesTheCountdown:
    def test_a_scanned_badge_reports_the_time_left(self, holder):
        qrCode = generateBadgeQr(holder, expiresInSeconds=120).json()

        response = holder.post(
            "/verifications/badge",
            json={"scannedValue": qrCode["token"]},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["result"] == "pass"
        assert 0 < body["remainingSeconds"] <= 120

    def test_an_expired_badge_reports_no_time_left(self, holder):
        qrCode = generateBadgeQr(holder).json()
        expiredAt = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()

        response = holder.post(
            "/verifications/badge",
            json={"scannedValue": reSignWithExpiry(qrCode["token"], expiredAt)},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["result"] == "fail"
        assert body["reasons"] == ["expired"]
        assert body["remainingSeconds"] == 0

    def test_an_unreadable_token_reports_no_countdown(self, holder):
        response = holder.post(
            "/verifications/badge",
            json={"scannedValue": "not-a-token"},
        )

        assert response.status_code == 200
        assert response.json()["remainingSeconds"] is None

    def test_a_scanned_age_proof_reports_the_time_left(self, holder):
        qrCode = generateAgeProofQr(holder, expiresInSeconds=90).json()

        response = holder.get(f"/verifications/age-proof/{qrCode['token']}")

        assert response.status_code == 200
        assert 0 < response.json()["remainingSeconds"] <= 90

    def test_an_expired_age_proof_is_still_gone(self, holder, mongoDatabase):
        qrCode = generateAgeProofQr(holder).json()
        expiredAt = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        mongoDatabase.age_proof_tokens.update_one(
            {},
            {"$set": {"expires_at": expiredAt}},
        )

        response = holder.get(f"/verifications/age-proof/{qrCode['token']}")

        assert response.status_code == 410
