from datetime import datetime, timedelta


ADMIN_ID = "900000001"
ADMIN_PIN = "481726"
HOLDER_ID = "123456789"
HOLDER_PIN = "281992"


def registerUser(
    client,
    institutionalId: str = HOLDER_ID,
    role: str = "student",
) -> object:
    return client.post(
        "/users/institutional-identities",
        json={
            "fullName": "Kevin Picado",
            "email": f"{institutionalId}@utn.ac.cr",
            "role": role,
            "institutionalId": institutionalId,
        },
    )


def setPin(client, institutionalId: str, pin: str) -> object:
    return client.post(
        f"/users/{institutionalId}/pin",
        json={"pin": pin, "pinConfirm": pin},
    )


def createAdmin(client, institutionalId: str = ADMIN_ID, pin: str = ADMIN_PIN) -> None:
    registerUser(client, institutionalId=institutionalId, role="admin")
    setPin(client, institutionalId, pin)


def createHolder(
    client,
    institutionalId: str = HOLDER_ID,
    role: str = "student",
    pin: str = HOLDER_PIN,
) -> None:
    registerUser(client, institutionalId=institutionalId, role=role)
    setPin(client, institutionalId, pin)


def issueBadge(
    client,
    institutionalId: str = HOLDER_ID,
    adminInstitutionalId: str = ADMIN_ID,
    adminPin: str = ADMIN_PIN,
    roleType: str | None = None,
    validForDays: int | None = None,
) -> object:
    payload: dict = {
        "adminInstitutionalId": adminInstitutionalId,
        "adminPin": adminPin,
        "institutionalId": institutionalId,
    }
    if roleType is not None:
        payload["roleType"] = roleType
    if validForDays is not None:
        payload["validForDays"] = validForDays

    return client.post("/badges", json=payload)


def fetchDeliveries(
    client,
    institutionalId: str = HOLDER_ID,
    pin: str = HOLDER_PIN,
) -> object:
    return client.post(
        f"/users/{institutionalId}/badge-deliveries/fetch",
        json={"pin": pin},
    )


def acknowledgeDelivery(
    client,
    deliveryId: str,
    institutionalId: str = HOLDER_ID,
    pin: str = HOLDER_PIN,
) -> object:
    return client.post(
        f"/users/{institutionalId}/badge-deliveries/{deliveryId}/acknowledge",
        json={"pin": pin},
    )


class TestAdminAuthorization:
    def test_admin_can_issue_a_badge(self, client):
        createAdmin(client)
        createHolder(client)

        response = issueBadge(client)

        assert response.status_code == 201
        assert response.json()["message"] == "Badge issued successfully"

    def test_non_admin_cannot_issue_a_badge(self, client):
        createHolder(client, institutionalId="222222222", role="staff", pin="375849")
        createHolder(client)

        response = issueBadge(
            client,
            adminInstitutionalId="222222222",
            adminPin="375849",
        )

        assert response.status_code == 403
        assert response.json()["detail"] == "Only an institutional admin can issue badges"

    def test_issuing_rejects_wrong_admin_pin(self, client):
        createAdmin(client)
        createHolder(client)

        response = issueBadge(client, adminPin="999999")

        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid PIN"

    def test_issuing_requires_the_admin_to_have_a_pin(self, client):
        registerUser(client, institutionalId=ADMIN_ID, role="admin")
        createHolder(client)

        response = issueBadge(client)

        assert response.status_code == 409
        assert "No PIN has been set" in response.json()["detail"]

    def test_issuing_rejects_unknown_admin(self, client):
        createHolder(client)

        response = issueBadge(client, adminInstitutionalId="999999999")

        assert response.status_code == 404
        assert response.json()["detail"] == "User not found"

    def test_issuing_rejects_malformed_admin_id(self, client):
        response = issueBadge(client, adminInstitutionalId="ABC-123")

        assert response.status_code == 422


class TestBadgeCreation:
    def test_badge_is_tied_to_the_holder(self, client, mongoDatabase):
        createAdmin(client)
        createHolder(client)

        body = issueBadge(client).json()

        holder = mongoDatabase.users.find_one({"institutional_id": HOLDER_ID})
        badge = mongoDatabase.badges.find_one({"id": body["badge"]["id"]})
        assert badge["user_id"] == holder["id"]
        assert body["badge"]["userId"] == holder["id"]
        assert body["badge"]["status"] == "issued"
        assert body["badge"]["badgeCode"].startswith(f"BADGE-{HOLDER_ID}-")

    def test_issuance_records_the_admin_who_performed_it(self, client, mongoDatabase):
        createAdmin(client)
        createHolder(client)

        body = issueBadge(client).json()

        admin = mongoDatabase.users.find_one({"institutional_id": ADMIN_ID})
        badge = mongoDatabase.badges.find_one({"id": body["badge"]["id"]})
        assert badge["issued_by_user_id"] == admin["id"]

    def test_role_type_defaults_to_the_holder_role(self, client):
        createAdmin(client)
        createHolder(client, role="professor")

        body = issueBadge(client).json()

        assert body["badge"]["roleType"] == "professor"

    def test_admin_can_set_a_different_role_type(self, client):
        createAdmin(client)
        createHolder(client, role="student")

        body = issueBadge(client, roleType="staff").json()

        assert body["badge"]["roleType"] == "staff"

    def test_role_type_rejects_unknown_value(self, client):
        createAdmin(client)
        createHolder(client)

        response = issueBadge(client, roleType="visitor")

        assert response.status_code == 422

    def test_badge_is_valid_for_one_year_by_default(self, client):
        createAdmin(client)
        createHolder(client)

        badge = issueBadge(client).json()["badge"]

        validFrom = datetime.fromisoformat(badge["validFrom"])
        validUntil = datetime.fromisoformat(badge["validUntil"])
        assert validUntil - validFrom == timedelta(days=365)

    def test_admin_can_set_the_validity_period(self, client):
        createAdmin(client)
        createHolder(client)

        badge = issueBadge(client, validForDays=30).json()["badge"]

        validFrom = datetime.fromisoformat(badge["validFrom"])
        validUntil = datetime.fromisoformat(badge["validUntil"])
        assert validUntil - validFrom == timedelta(days=30)

    def test_validity_period_outside_the_allowed_range_is_rejected(self, client):
        createAdmin(client)
        createHolder(client)

        tooShort = issueBadge(client, validForDays=0)
        tooLong = issueBadge(client, validForDays=5000)

        assert tooShort.status_code == 422
        assert tooLong.status_code == 422

    def test_issuing_rejects_unknown_holder(self, client):
        createAdmin(client)

        response = issueBadge(client, institutionalId="999999999")

        assert response.status_code == 404
        assert response.json()["detail"] == "Badge holder was not found"

    def test_issuing_rejects_inactive_holder(self, client, mongoDatabase):
        createAdmin(client)
        createHolder(client)
        mongoDatabase.users.update_one(
            {"institutional_id": HOLDER_ID},
            {"$set": {"is_active": False}},
        )

        response = issueBadge(client)

        assert response.status_code == 404
        assert "not active" in response.json()["detail"]

    def test_each_issued_badge_gets_its_own_code(self, client):
        createAdmin(client)
        createHolder(client)

        firstCode = issueBadge(client).json()["badge"]["badgeCode"]
        secondCode = issueBadge(client).json()["badge"]["badgeCode"]

        assert firstCode != secondCode


class TestSupersedingPreviousBadges:
    def test_issuing_supersedes_the_registration_badge(self, client, mongoDatabase):
        createAdmin(client)
        registrationBadgeId = registerUser(client).json()["badge"]["id"]
        setPin(client, HOLDER_ID, HOLDER_PIN)

        body = issueBadge(client).json()

        assert body["supersededBadgeId"] == registrationBadgeId
        supersededBadge = mongoDatabase.badges.find_one({"id": registrationBadgeId})
        assert supersededBadge["status"] == "superseded"

    def test_badge_profile_shows_the_newly_issued_badge(self, client):
        createAdmin(client)
        createHolder(client)

        newBadge = issueBadge(client, roleType="staff").json()["badge"]
        profile = client.get(f"/users/{HOLDER_ID}/badge-profile").json()

        assert profile["badgeCode"] == newBadge["badgeCode"]
        assert profile["roleType"] == "staff"
        assert profile["status"] == "issued"

    def test_only_one_badge_stays_active(self, client, mongoDatabase):
        createAdmin(client)
        createHolder(client)

        issueBadge(client)
        issueBadge(client)

        holder = mongoDatabase.users.find_one({"institutional_id": HOLDER_ID})
        activeBadges = mongoDatabase.badges.count_documents(
            {"user_id": holder["id"], "status": "issued"}
        )
        assert activeBadges == 1
        assert mongoDatabase.badges.count_documents({"user_id": holder["id"]}) == 3

    def test_superseded_badge_id_is_null_when_no_active_badge_exists(
        self,
        client,
        mongoDatabase,
    ):
        createAdmin(client)
        createHolder(client)
        mongoDatabase.badges.update_many(
            {"badge_code": {"$regex": f"^BADGE-{HOLDER_ID}-"}},
            {"$set": {"status": "revoked"}},
        )

        body = issueBadge(client).json()

        assert body["supersededBadgeId"] is None

    def test_verification_qr_of_a_superseded_badge_stops_passing(self, client):
        createAdmin(client)
        createHolder(client)

        qr = client.post(
            f"/users/{HOLDER_ID}/verification-qr",
            json={"pin": HOLDER_PIN},
        ).json()
        issueBadge(client)

        verification = client.post(
            "/verifications/badge",
            json={"scannedValue": qr["token"]},
        ).json()

        assert verification["result"] == "fail"
        assert verification["signatureValid"] is True
        assert verification["reasons"] == ["badge_not_active"]
        assert verification["badgeStatus"] == "superseded"

    def test_verification_qr_of_the_new_badge_passes(self, client):
        createAdmin(client)
        createHolder(client)
        issueBadge(client)

        qr = client.post(
            f"/users/{HOLDER_ID}/verification-qr",
            json={"pin": HOLDER_PIN},
        ).json()
        verification = client.post(
            "/verifications/badge",
            json={"scannedValue": qr["token"]},
        ).json()

        assert verification["result"] == "pass"


class TestBadgeDeliveryToDevice:
    def test_issuance_triggers_a_pending_delivery(self, client):
        createAdmin(client)
        createHolder(client)

        body = issueBadge(client).json()

        delivery = body["delivery"]
        assert delivery["status"] == "pending"
        assert delivery["badgeId"] == body["badge"]["id"]
        assert delivery["badgeCode"] == body["badge"]["badgeCode"]
        assert delivery["deliveredAt"] is None

    def test_registration_also_triggers_a_delivery(self, client):
        createHolder(client)

        deliveries = fetchDeliveries(client).json()["deliveries"]

        assert len(deliveries) == 1
        assert deliveries[0]["status"] == "pending"

    def test_device_fetches_the_pending_delivery(self, client):
        createAdmin(client)
        createHolder(client)
        issued = issueBadge(client).json()

        response = fetchDeliveries(client)

        assert response.status_code == 200
        body = response.json()
        assert body["institutionalId"] == HOLDER_ID
        assert [item["deliveryId"] for item in body["deliveries"]] == [
            issued["delivery"]["deliveryId"]
        ]

    def test_device_acknowledges_the_delivery(self, client):
        createAdmin(client)
        createHolder(client)
        deliveryId = issueBadge(client).json()["delivery"]["deliveryId"]

        response = acknowledgeDelivery(client, deliveryId)

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "delivered"
        assert body["deliveredAt"] is not None

    def test_acknowledged_delivery_is_no_longer_pending(self, client):
        createAdmin(client)
        createHolder(client)
        deliveryId = issueBadge(client).json()["delivery"]["deliveryId"]

        acknowledgeDelivery(client, deliveryId)
        deliveries = fetchDeliveries(client).json()["deliveries"]

        assert deliveries == []

    def test_acknowledging_twice_keeps_the_first_delivery_time(self, client):
        createAdmin(client)
        createHolder(client)
        deliveryId = issueBadge(client).json()["delivery"]["deliveryId"]

        first = acknowledgeDelivery(client, deliveryId).json()
        second = acknowledgeDelivery(client, deliveryId).json()

        assert second["status"] == "delivered"
        assert second["deliveredAt"] == first["deliveredAt"]

    def test_reissuing_supersedes_a_delivery_the_device_never_collected(self, client):
        createAdmin(client)
        createHolder(client)
        staleDeliveryId = issueBadge(client).json()["delivery"]["deliveryId"]

        freshDeliveryId = issueBadge(client).json()["delivery"]["deliveryId"]
        pending = fetchDeliveries(client).json()["deliveries"]

        assert [item["deliveryId"] for item in pending] == [freshDeliveryId]
        assert staleDeliveryId != freshDeliveryId

    def test_fetching_deliveries_requires_the_holder_pin(self, client):
        createAdmin(client)
        createHolder(client)
        issueBadge(client)

        response = fetchDeliveries(client, pin="999999")

        assert response.status_code == 401

    def test_acknowledging_rejects_unknown_delivery(self, client):
        createHolder(client)

        response = acknowledgeDelivery(client, "does-not-exist")

        assert response.status_code == 404
        assert response.json()["detail"] == "Badge delivery was not found"

    def test_a_holder_cannot_acknowledge_another_holders_delivery(self, client):
        createAdmin(client)
        createHolder(client)
        createHolder(client, institutionalId="222222222", pin="375849")
        deliveryId = issueBadge(client).json()["delivery"]["deliveryId"]

        response = acknowledgeDelivery(
            client,
            deliveryId,
            institutionalId="222222222",
            pin="375849",
        )

        assert response.status_code == 404

    def test_deliveries_are_scoped_to_the_holder(self, client):
        createAdmin(client)
        createHolder(client)
        createHolder(client, institutionalId="222222222", pin="375849")
        issueBadge(client)

        otherDeliveries = fetchDeliveries(
            client,
            institutionalId="222222222",
            pin="375849",
        ).json()["deliveries"]

        assert len(otherDeliveries) == 1
        assert otherDeliveries[0]["badgeCode"].startswith("BADGE-222222222-")
