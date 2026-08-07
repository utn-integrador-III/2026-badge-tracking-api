from datetime import datetime, timezone

import pytest


ADMIN_ID = "900000001"
ADMIN_PIN = "481726"
HOLDER_ID = "123456789"
HOLDER_PIN = "281992"
OTHER_HOLDER_ID = "222222222"
SIGNING_KEY = "test-only-signing-key-with-at-least-32-bytes"


def registerUser(
    client,
    institutionalId: str,
    *,
    fullName: str,
    email: str,
    role: str = "student",
    birthDate: str | None = None,
) -> dict:
    payload = {
        "fullName": fullName,
        "email": email,
        "role": role,
        "institutionalId": institutionalId,
    }
    if birthDate is not None:
        payload["birthDate"] = birthDate

    response = client.post("/users/institutional-identities", json=payload)
    assert response.status_code == 201
    return response.json()


def setPin(client, institutionalId: str, pin: str) -> None:
    response = client.post(
        f"/users/{institutionalId}/pin",
        json={"pin": pin, "pinConfirm": pin},
    )
    assert response.status_code == 201


def createAdmin(client) -> dict:
    registration = registerUser(
        client,
        ADMIN_ID,
        fullName="Institutional Administrator",
        email="admin@utn.ac.cr",
        role="admin",
    )
    setPin(client, ADMIN_ID, ADMIN_PIN)
    return registration


def createHolder(
    client,
    institutionalId: str = HOLDER_ID,
    *,
    fullName: str = "Kevin Picado",
    email: str = "kevin.picado@utn.ac.cr",
    birthDate: str | None = "1992-08-28",
) -> dict:
    registration = registerUser(
        client,
        institutionalId,
        fullName=fullName,
        email=email,
        birthDate=birthDate,
    )
    setPin(client, institutionalId, HOLDER_PIN)
    return registration


def searchBadges(
    client,
    query: str,
    *,
    adminInstitutionalId: str = ADMIN_ID,
    adminPin: str = ADMIN_PIN,
    limit: int | None = None,
):
    payload = {
        "adminInstitutionalId": adminInstitutionalId,
        "adminPin": adminPin,
        "query": query,
    }
    if limit is not None:
        payload["limit"] = limit
    return client.post("/badges/search", json=payload)


def updateBadgeStatus(
    client,
    badgeId: int,
    lifecycleStatus: str,
    *,
    reason: str = "Graduation completed",
    adminInstitutionalId: str = ADMIN_ID,
    adminPin: str = ADMIN_PIN,
):
    return client.patch(
        f"/badges/{badgeId}/status",
        json={
            "adminInstitutionalId": adminInstitutionalId,
            "adminPin": adminPin,
            "status": lifecycleStatus,
            "reason": reason,
        },
    )


def issueBadge(client, institutionalId: str = HOLDER_ID):
    return client.post(
        "/badges",
        json={
            "adminInstitutionalId": ADMIN_ID,
            "adminPin": ADMIN_PIN,
            "institutionalId": institutionalId,
        },
    )


def assertAwareIsoTimestamp(value: str) -> None:
    parsedValue = datetime.fromisoformat(value)
    assert parsedValue.tzinfo is not None
    assert parsedValue.utcoffset() is not None


class TestAdminBadgeSearch:
    @pytest.mark.parametrize(
        "query",
        [
            HOLDER_ID,
            "Kevin Picado",
            "PICADO",
            "KEVIN.PICADO@UTN.AC.CR",
        ],
    )
    def test_admin_searches_by_id_name_or_email(self, client, query):
        createAdmin(client)
        registration = createHolder(client)

        response = searchBadges(client, query)

        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 1
        assert len(body["results"]) == 1
        result = body["results"][0]
        assert result == {
            "userId": registration["user"]["id"],
            "fullName": "Kevin Picado",
            "email": "kevin.picado@utn.ac.cr",
            "institutionalId": HOLDER_ID,
            "role": "student",
            "isActive": True,
            "badge": registration["badge"],
        }

    def test_search_treats_regex_characters_as_literal_text(self, client):
        createAdmin(client)
        createHolder(client)

        response = searchBadges(client, ".*")

        assert response.status_code == 200
        assert response.json() == {"count": 0, "results": []}

    def test_search_returns_a_user_without_a_badge(self, client, mongoDatabase):
        createAdmin(client)
        registration = createHolder(client)
        mongoDatabase.badges.delete_many({"user_id": registration["user"]["id"]})

        response = searchBadges(client, HOLDER_ID)

        assert response.status_code == 200
        result = response.json()["results"][0]
        assert result["institutionalId"] == HOLDER_ID
        assert result["badge"] is None

    def test_search_honors_the_result_limit(self, client):
        createAdmin(client)
        createHolder(client)
        createHolder(
            client,
            OTHER_HOLDER_ID,
            fullName="Kevin Vargas",
            email="kevin.vargas@utn.ac.cr",
        )

        response = searchBadges(client, "Kevin", limit=1)

        assert response.status_code == 200
        assert response.json()["count"] == 1
        assert len(response.json()["results"]) == 1

    def test_search_returns_the_most_recent_badge(self, client):
        createAdmin(client)
        registration = createHolder(client)
        newestBadge = issueBadge(client).json()["badge"]

        response = searchBadges(client, HOLDER_ID)

        assert response.status_code == 200
        result = response.json()["results"][0]
        assert result["badge"] == newestBadge
        assert result["badge"]["id"] != registration["badge"]["id"]

    def test_search_supports_legacy_badge_documents(self, client, mongoDatabase):
        createAdmin(client)
        holder = createHolder(client)
        mongoDatabase.badges.update_one(
            {"id": holder["badge"]["id"]},
            {"$unset": {"role_type": "", "valid_from": "", "valid_until": ""}},
        )

        response = searchBadges(client, HOLDER_ID)

        assert response.status_code == 200
        badge = response.json()["results"][0]["badge"]
        assert badge["roleType"] == "student"
        assert badge["validFrom"] == badge["issuedAt"]
        assert (
            datetime.fromisoformat(badge["validUntil"])
            - datetime.fromisoformat(badge["validFrom"])
        ).days == 365

    def test_search_applies_length_limits_after_trimming(self, client):
        createAdmin(client)

        response = searchBadges(client, f" {'x' * 150} ")

        assert response.status_code == 200
        assert response.json() == {"count": 0, "results": []}

    def test_non_admin_cannot_search_badge_holders(self, client):
        createHolder(client)

        response = searchBadges(
            client,
            HOLDER_ID,
            adminInstitutionalId=HOLDER_ID,
            adminPin=HOLDER_PIN,
        )

        assert response.status_code == 403

    def test_search_rejects_an_invalid_admin_pin(self, client):
        createAdmin(client)
        createHolder(client)

        response = searchBadges(client, HOLDER_ID, adminPin="999999")

        assert response.status_code == 401

    @pytest.mark.parametrize(
        ("query", "limit"),
        [
            (" ", None),
            ("x", None),
            ("Kevin", 0),
            ("Kevin", 51),
        ],
    )
    def test_search_validates_query_and_limit(self, client, query, limit):
        createAdmin(client)

        response = searchBadges(client, query, limit=limit)

        assert response.status_code == 422


class TestBadgeLifecycleAuthorization:
    def test_non_admin_cannot_change_badge_status(self, client):
        holder = createHolder(client)

        response = updateBadgeStatus(
            client,
            holder["badge"]["id"],
            "revoked",
            adminInstitutionalId=HOLDER_ID,
            adminPin=HOLDER_PIN,
        )

        assert response.status_code == 403

    def test_non_admin_cannot_probe_an_unknown_badge(self, client):
        createHolder(client)

        response = updateBadgeStatus(
            client,
            999999,
            "revoked",
            adminInstitutionalId=HOLDER_ID,
            adminPin=HOLDER_PIN,
        )

        assert response.status_code == 403

    def test_status_change_rejects_an_invalid_admin_pin(self, client):
        createAdmin(client)
        holder = createHolder(client)

        response = updateBadgeStatus(
            client,
            holder["badge"]["id"],
            "revoked",
            adminPin="999999",
        )

        assert response.status_code == 401

    def test_status_change_rejects_an_unknown_badge(self, client):
        createAdmin(client)

        response = updateBadgeStatus(client, 999999, "revoked")

        assert response.status_code == 404

    @pytest.mark.parametrize("adminStatus", ["suspended", "revoked"])
    def test_inactive_admin_badge_removes_management_access(
        self,
        client,
        adminStatus,
    ):
        admin = createAdmin(client)
        createHolder(client)
        lifecycleResponse = updateBadgeStatus(
            client,
            admin["badge"]["id"],
            adminStatus,
            reason="Administrator access withdrawn",
        )
        assert lifecycleResponse.status_code == 200

        response = searchBadges(client, HOLDER_ID)

        assert response.status_code == 403

    @pytest.mark.parametrize("badgeId", [0, -1])
    def test_status_change_rejects_non_positive_badge_id(self, client, badgeId):
        response = updateBadgeStatus(client, badgeId, "revoked")

        assert response.status_code == 422


class TestBadgeLifecycleChanges:
    @pytest.mark.parametrize("lifecycleStatus", ["suspended", "revoked"])
    def test_admin_changes_status_and_records_an_audit_trail(
        self,
        client,
        mongoDatabase,
        lifecycleStatus,
    ):
        admin = createAdmin(client)
        holder = createHolder(client)
        badgeId = holder["badge"]["id"]

        response = updateBadgeStatus(
            client,
            badgeId,
            lifecycleStatus,
            reason="  Graduation completed  ",
        )

        assert response.status_code == 200
        body = response.json()
        assert body["message"]
        assert body["badge"]["id"] == badgeId
        assert body["badge"]["status"] == lifecycleStatus
        assert body["previousStatus"] == "issued"
        assert body["changed"] is True
        assert body["reason"] == "Graduation completed"
        assertAwareIsoTimestamp(body["changedAt"])

        badge = mongoDatabase.badges.find_one({"id": badgeId})
        assert badge["status"] == lifecycleStatus
        assert badge["status_change_reason"] == "Graduation completed"
        assert badge["status_changed_at"] == body["changedAt"]
        assert badge["status_changed_by_user_id"] == admin["user"]["id"]
        assert len(badge["status_history"]) == 1
        historyEvent = badge["status_history"][0]
        assert historyEvent["previous_status"] == "issued"
        assert historyEvent["status"] == lifecycleStatus
        assert historyEvent["reason"] == "Graduation completed"
        assert historyEvent["changed_at"] == body["changedAt"]
        assert historyEvent["changed_by_user_id"] == admin["user"]["id"]
        assert len(historyEvent["event_id"]) == 32

        user = mongoDatabase.users.find_one({"id": holder["user"]["id"]})
        assert user["is_active"] is True

    @pytest.mark.parametrize("lifecycleStatus", ["suspended", "revoked"])
    def test_repeating_the_same_change_is_idempotent(
        self,
        client,
        mongoDatabase,
        lifecycleStatus,
    ):
        createAdmin(client)
        holder = createHolder(client)
        badgeId = holder["badge"]["id"]
        first = updateBadgeStatus(
            client,
            badgeId,
            lifecycleStatus,
            reason="Administrative decision",
        ).json()

        secondResponse = updateBadgeStatus(
            client,
            badgeId,
            lifecycleStatus,
            reason="A different reason that must not replace the original",
        )

        assert secondResponse.status_code == 200
        second = secondResponse.json()
        assert second["changed"] is False
        assert second["previousStatus"] == lifecycleStatus
        assert second["changedAt"] == first["changedAt"]
        assert second["reason"] == first["reason"]

        badge = mongoDatabase.badges.find_one({"id": badgeId})
        assert badge["status_changed_at"] == first["changedAt"]
        assert badge["status_change_reason"] == first["reason"]
        assert len(badge["status_history"]) == 1

    def test_a_suspended_badge_can_be_revoked(self, client, mongoDatabase):
        createAdmin(client)
        holder = createHolder(client)
        badgeId = holder["badge"]["id"]
        suspended = updateBadgeStatus(
            client,
            badgeId,
            "suspended",
            reason="Pending institutional review",
        ).json()

        response = updateBadgeStatus(
            client,
            badgeId,
            "revoked",
            reason="Review confirmed termination",
        )

        assert response.status_code == 200
        body = response.json()
        assert body["previousStatus"] == "suspended"
        assert body["badge"]["status"] == "revoked"
        assert body["changed"] is True
        assert body["reason"] == "Review confirmed termination"
        assertAwareIsoTimestamp(body["changedAt"])
        badge = mongoDatabase.badges.find_one({"id": badgeId})
        assert badge["status"] == "revoked"
        assert len(badge["status_history"]) == 2
        assert badge["status_history"][0]["changed_at"] == suspended["changedAt"]
        assert badge["status_history"][1]["changed_at"] == body["changedAt"]

    def test_legacy_active_badge_can_be_suspended(self, client, mongoDatabase):
        createAdmin(client)
        holder = createHolder(client)
        badgeId = holder["badge"]["id"]
        mongoDatabase.badges.update_one(
            {"id": badgeId},
            {"$set": {"status": "active"}},
        )

        response = updateBadgeStatus(client, badgeId, "suspended")

        assert response.status_code == 200
        assert response.json()["previousStatus"] == "active"
        assert response.json()["badge"]["status"] == "suspended"

    def test_concurrent_suspension_does_not_block_terminal_revocation(
        self,
        client,
        mongoDatabase,
        monkeypatch,
    ):
        import services.badge_management_service as managementService

        createAdmin(client)
        holder = createHolder(client)
        badgeId = holder["badge"]["id"]
        originalFindOneAndUpdate = mongoDatabase.badges.find_one_and_update
        firstAttempt = True

        def suspendBeforeFirstUpdate(*args, **kwargs):
            nonlocal firstAttempt
            if firstAttempt:
                firstAttempt = False
                mongoDatabase.badges.update_one(
                    {"id": badgeId},
                    {"$set": {"status": "suspended"}},
                )
                return None
            return originalFindOneAndUpdate(*args, **kwargs)

        monkeypatch.setattr(
            mongoDatabase.badges,
            "find_one_and_update",
            suspendBeforeFirstUpdate,
        )
        monkeypatch.setattr(managementService, "getDatabase", lambda: mongoDatabase)

        response = updateBadgeStatus(client, badgeId, "revoked")

        assert response.status_code == 200
        assert response.json()["previousStatus"] == "suspended"
        assert response.json()["badge"]["status"] == "revoked"

    def test_a_revoked_badge_cannot_transition_back_to_suspended(
        self,
        client,
        mongoDatabase,
    ):
        createAdmin(client)
        holder = createHolder(client)
        badgeId = holder["badge"]["id"]
        updateBadgeStatus(client, badgeId, "revoked")

        response = updateBadgeStatus(
            client,
            badgeId,
            "suspended",
            reason="Attempt to reopen a revoked badge",
        )

        assert response.status_code == 409
        assert mongoDatabase.badges.find_one({"id": badgeId})["status"] == "revoked"

    def test_a_superseded_badge_cannot_be_suspended(self, client, mongoDatabase):
        createAdmin(client)
        holder = createHolder(client)
        oldBadgeId = holder["badge"]["id"]
        issued = issueBadge(client)
        assert issued.status_code == 201
        oldBadge = mongoDatabase.badges.find_one({"id": oldBadgeId})
        assert oldBadge["status"] == "superseded"

        response = updateBadgeStatus(
            client,
            oldBadgeId,
            "suspended",
            reason="Attempt to alter an old badge",
        )

        assert response.status_code == 409
        oldBadge = mongoDatabase.badges.find_one({"id": oldBadgeId})
        assert oldBadge["status"] == "superseded"

    @pytest.mark.parametrize(
        ("lifecycleStatus", "reason"),
        [
            ("active", "Unsupported target status"),
            ("issued", "Unsupported target status"),
            ("revoked", " "),
            ("revoked", "no"),
            ("revoked", "x" * 251),
        ],
    )
    def test_status_change_validates_status_and_reason(
        self,
        client,
        lifecycleStatus,
        reason,
    ):
        createAdmin(client)
        holder = createHolder(client)

        response = updateBadgeStatus(
            client,
            holder["badge"]["id"],
            lifecycleStatus,
            reason=reason,
        )

        assert response.status_code == 422

    def test_reason_length_is_applied_after_trimming(self, client):
        createAdmin(client)
        holder = createHolder(client)

        response = updateBadgeStatus(
            client,
            holder["badge"]["id"],
            "revoked",
            reason=f" {'x' * 250} ",
        )

        assert response.status_code == 200
        assert response.json()["reason"] == "x" * 250

    @pytest.mark.parametrize("lifecycleStatus", ["suspended", "revoked"])
    def test_badge_profile_reflects_the_new_status(self, client, lifecycleStatus):
        createAdmin(client)
        holder = createHolder(client)
        updateBadgeStatus(client, holder["badge"]["id"], lifecycleStatus)

        response = client.get(f"/users/{HOLDER_ID}/badge-profile")

        assert response.status_code == 200
        assert response.json()["status"] == lifecycleStatus

    def test_search_reflects_revocation_without_deactivating_identity(self, client):
        createAdmin(client)
        holder = createHolder(client)
        updateBadgeStatus(client, holder["badge"]["id"], "revoked")

        response = searchBadges(client, HOLDER_ID)

        assert response.status_code == 200
        result = response.json()["results"][0]
        assert result["isActive"] is True
        assert result["badge"]["status"] == "revoked"


class TestImmediateInvalidation:
    @pytest.mark.parametrize("lifecycleStatus", ["suspended", "revoked"])
    def test_previously_issued_qr_credentials_fail_immediately(
        self,
        client,
        monkeypatch,
        lifecycleStatus,
    ):
        monkeypatch.setenv("BADGE_TRACKING_SIGNING_KEY", SIGNING_KEY)
        createAdmin(client)
        holder = createHolder(client)
        verificationQr = client.post(
            f"/users/{HOLDER_ID}/verification-qr",
            json={"pin": HOLDER_PIN},
        )
        ageProofQr = client.post(
            f"/users/{HOLDER_ID}/age-proof-qr",
            json={"pin": HOLDER_PIN},
        )
        assert verificationQr.status_code == 201
        assert ageProofQr.status_code == 201

        lifecycleResponse = updateBadgeStatus(
            client,
            holder["badge"]["id"],
            lifecycleStatus,
        )
        assert lifecycleResponse.status_code == 200

        verification = client.post(
            "/verifications/badge",
            json={"scannedValue": verificationQr.json()["token"]},
        )
        ageProof = client.get(
            f"/verifications/age-proof/{ageProofQr.json()['token']}"
        )

        assert verification.status_code == 200
        assert verification.json()["result"] == "fail"
        assert verification.json()["signatureValid"] is True
        assert verification.json()["reasons"] == ["badge_not_active"]
        assert verification.json()["badgeStatus"] == lifecycleStatus
        assert ageProof.status_code == 200
        assert ageProof.json()["valid"] is False
        assert ageProof.json()["badgeStatus"] == lifecycleStatus

    @pytest.mark.parametrize("lifecycleStatus", ["suspended", "revoked"])
    def test_inactive_badge_cannot_generate_new_proofs(
        self,
        client,
        monkeypatch,
        lifecycleStatus,
    ):
        monkeypatch.setenv("BADGE_TRACKING_SIGNING_KEY", SIGNING_KEY)
        createAdmin(client)
        holder = createHolder(client)
        updateBadgeStatus(client, holder["badge"]["id"], lifecycleStatus)

        verificationQr = client.post(
            f"/users/{HOLDER_ID}/verification-qr",
            json={"pin": HOLDER_PIN},
        )
        ageProofQr = client.post(
            f"/users/{HOLDER_ID}/age-proof-qr",
            json={"pin": HOLDER_PIN},
        )

        assert verificationQr.status_code == 409
        assert lifecycleStatus in verificationQr.json()["detail"]
        assert ageProofQr.status_code == 409
        assert lifecycleStatus in ageProofQr.json()["detail"]


class TestDeliveryAndReissuance:
    @pytest.mark.parametrize("lifecycleStatus", ["suspended", "revoked"])
    def test_pending_delivery_is_cancelled(
        self,
        client,
        mongoDatabase,
        lifecycleStatus,
    ):
        createAdmin(client)
        holder = createHolder(client)
        badgeId = holder["badge"]["id"]
        delivery = mongoDatabase.badge_deliveries.find_one({"badge_id": badgeId})
        assert delivery["status"] == "pending"

        response = updateBadgeStatus(client, badgeId, lifecycleStatus)

        assert response.status_code == 200
        cancelledDelivery = mongoDatabase.badge_deliveries.find_one(
            {"delivery_id": delivery["delivery_id"]}
        )
        assert cancelledDelivery["status"] == "cancelled"
        assert cancelledDelivery["cancellation_reason"] == "Graduation completed"
        assertAwareIsoTimestamp(cancelledDelivery["cancelled_at"])

        pending = client.post(
            f"/users/{HOLDER_ID}/badge-deliveries/fetch",
            json={"pin": HOLDER_PIN},
        )
        assert pending.status_code == 200
        assert pending.json()["deliveries"] == []

        acknowledge = client.post(
            (
                f"/users/{HOLDER_ID}/badge-deliveries/"
                f"{delivery['delivery_id']}/acknowledge"
            ),
            json={"pin": HOLDER_PIN},
        )
        assert acknowledge.status_code == 200
        assert acknowledge.json()["status"] == "cancelled"
        assert mongoDatabase.badge_deliveries.find_one(
            {"delivery_id": delivery["delivery_id"]}
        )["status"] == "cancelled"

    def test_admin_can_reissue_after_revocation(self, client, mongoDatabase):
        createAdmin(client)
        holder = createHolder(client)
        revokedBadgeId = holder["badge"]["id"]
        updateBadgeStatus(client, revokedBadgeId, "revoked")

        response = issueBadge(client)

        assert response.status_code == 201
        body = response.json()
        assert body["supersededBadgeId"] is None
        assert body["badge"]["id"] != revokedBadgeId
        assert body["badge"]["status"] == "issued"
        revokedBadge = mongoDatabase.badges.find_one({"id": revokedBadgeId})
        assert revokedBadge["status"] == "revoked"

        user = mongoDatabase.users.find_one({"id": holder["user"]["id"]})
        assert user["is_active"] is True
        profile = client.get(f"/users/{HOLDER_ID}/badge-profile")
        assert profile.status_code == 200
        assert profile.json()["badgeCode"] == body["badge"]["badgeCode"]
        assert profile.json()["status"] == "issued"

    def test_reissue_does_not_overwrite_a_concurrent_revocation(
        self,
        client,
        mongoDatabase,
        monkeypatch,
    ):
        import services.badge_issuance_service as issuanceService

        createAdmin(client)
        holder = createHolder(client)
        oldBadgeId = holder["badge"]["id"]
        originalFindCurrentBadge = issuanceService.findCurrentBadge

        def findThenRevoke(userId, projection):
            badge = originalFindCurrentBadge(userId, projection)
            mongoDatabase.badges.update_one(
                {"id": badge["id"]},
                {"$set": {"status": "revoked"}},
            )
            return badge

        monkeypatch.setattr(
            issuanceService,
            "findCurrentBadge",
            findThenRevoke,
        )

        response = issueBadge(client)

        assert response.status_code == 201
        assert response.json()["supersededBadgeId"] is None
        assert mongoDatabase.badges.find_one({"id": oldBadgeId})["status"] == "revoked"

    @pytest.mark.parametrize("lifecycleStatus", ["suspended", "revoked"])
    def test_delivered_badge_record_is_preserved(
        self,
        client,
        mongoDatabase,
        lifecycleStatus,
    ):
        createAdmin(client)
        holder = createHolder(client)
        badgeId = holder["badge"]["id"]
        delivery = mongoDatabase.badge_deliveries.find_one({"badge_id": badgeId})
        acknowledge = client.post(
            (
                f"/users/{HOLDER_ID}/badge-deliveries/"
                f"{delivery['delivery_id']}/acknowledge"
            ),
            json={"pin": HOLDER_PIN},
        )
        assert acknowledge.status_code == 200
        deliveredAt = acknowledge.json()["deliveredAt"]

        response = updateBadgeStatus(client, badgeId, lifecycleStatus)

        assert response.status_code == 200
        storedDelivery = mongoDatabase.badge_deliveries.find_one(
            {"delivery_id": delivery["delivery_id"]}
        )
        assert storedDelivery["status"] == "delivered"
        assert storedDelivery["delivered_at"] == deliveredAt

    def test_concurrent_acknowledgement_cannot_deliver_an_inactive_badge(
        self,
        client,
        mongoDatabase,
    ):
        createAdmin(client)
        holder = createHolder(client)
        badgeId = holder["badge"]["id"]
        delivery = mongoDatabase.badge_deliveries.find_one({"badge_id": badgeId})
        revoked = updateBadgeStatus(client, badgeId, "revoked").json()
        acknowledgedAt = datetime.now(timezone.utc).isoformat()
        mongoDatabase.badge_deliveries.update_one(
            {"delivery_id": delivery["delivery_id"]},
            {
                "$set": {
                    "status": "delivered",
                    "delivered_at": acknowledgedAt,
                }
            },
        )
        assert acknowledgedAt >= revoked["changedAt"]

        response = client.post(
            (
                f"/users/{HOLDER_ID}/badge-deliveries/"
                f"{delivery['delivery_id']}/acknowledge"
            ),
            json={"pin": HOLDER_PIN},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"
        storedDelivery = mongoDatabase.badge_deliveries.find_one(
            {"delivery_id": delivery["delivery_id"]}
        )
        assert storedDelivery["status"] == "cancelled"
        assert storedDelivery["delivered_at"] is None
