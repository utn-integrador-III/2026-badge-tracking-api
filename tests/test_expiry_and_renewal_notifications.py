from datetime import datetime, timedelta, timezone

import pytest


ADMIN_ID = "900000001"
ADMIN_PIN = "481726"
HOLDER_ID = "123456789"
HOLDER_PIN = "281992"
OTHER_HOLDER_ID = "222222222"
OTHER_HOLDER_PIN = "371883"


def registerUser(
    client,
    institutionalId: str,
    *,
    fullName: str,
    email: str,
    role: str = "student",
) -> dict:
    response = client.post(
        "/users/institutional-identities",
        json={
            "fullName": fullName,
            "email": email,
            "role": role,
            "institutionalId": institutionalId,
        },
    )
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
    pin: str = HOLDER_PIN,
) -> dict:
    registration = registerUser(
        client,
        institutionalId,
        fullName=fullName,
        email=email,
    )
    setPin(client, institutionalId, pin)
    return registration


def moveExpiry(mongoDatabase, badgeId: int, **offset) -> str:
    """Place a badge's expiry at a chosen distance from now."""
    validUntil = (datetime.now(timezone.utc) + timedelta(**offset)).isoformat()
    mongoDatabase.badges.update_one(
        {"id": badgeId},
        {"$set": {"valid_until": validUntil}},
    )
    return validUntil


def fetchNotifications(
    client,
    institutionalId: str = HOLDER_ID,
    pin: str = HOLDER_PIN,
):
    return client.post(
        f"/users/{institutionalId}/badge-notifications/fetch",
        json={"pin": pin},
    )


def acknowledgeNotification(
    client,
    notificationId: str,
    institutionalId: str = HOLDER_ID,
    pin: str = HOLDER_PIN,
):
    return client.post(
        f"/users/{institutionalId}/badge-notifications/{notificationId}/acknowledge",
        json={"pin": pin},
    )


def dismissNotification(
    client,
    notificationId: str,
    institutionalId: str = HOLDER_ID,
    pin: str = HOLDER_PIN,
):
    return client.post(
        f"/users/{institutionalId}/badge-notifications/{notificationId}/dismiss",
        json={"pin": pin},
    )


def requestRenewal(
    client,
    institutionalId: str = HOLDER_ID,
    pin: str = HOLDER_PIN,
):
    return client.post(
        f"/users/{institutionalId}/badge-renewals",
        json={"pin": pin},
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


def updateBadgeStatus(client, badgeId: int, lifecycleStatus: str):
    return client.patch(
        f"/badges/{badgeId}/status",
        json={
            "adminInstitutionalId": ADMIN_ID,
            "adminPin": ADMIN_PIN,
            "status": lifecycleStatus,
            "reason": "Graduation completed",
        },
    )


def expiringHolder(client, mongoDatabase, *, days: int = 29) -> dict:
    """A holder whose badge already entered the renewal window."""
    registration = createHolder(client)
    registration["validUntil"] = moveExpiry(
        mongoDatabase,
        registration["badge"]["id"],
        days=days,
    )
    return registration


def assertAwareIsoTimestamp(value: str) -> None:
    parsedValue = datetime.fromisoformat(value)
    assert parsedValue.tzinfo is not None
    assert parsedValue.utcoffset() is not None


class TestExpiryNotice:
    def test_a_badge_far_from_expiry_raises_no_notification(self, client):
        createHolder(client)

        response = fetchNotifications(client)

        assert response.status_code == 200
        assert response.json() == {
            "institutionalId": HOLDER_ID,
            "notifications": [],
        }

    def test_holder_is_notified_inside_the_renewal_window(
        self,
        client,
        mongoDatabase,
    ):
        registration = expiringHolder(client, mongoDatabase)

        response = fetchNotifications(client)

        assert response.status_code == 200
        body = response.json()
        assert body["institutionalId"] == HOLDER_ID
        assert len(body["notifications"]) == 1
        notification = body["notifications"][0]
        assert len(notification["notificationId"]) == 32
        assert notification["type"] == "badge_expiring"
        assert notification["status"] == "pending"
        assert notification["badgeId"] == registration["badge"]["id"]
        assert notification["badgeCode"] == registration["badge"]["badgeCode"]
        assert notification["daysUntilExpiry"] == 29
        assert notification["expired"] is False
        assert notification["validUntil"] == registration["validUntil"]
        assert notification["deliveredAt"] is None
        assertAwareIsoTimestamp(notification["createdAt"])

    def test_notification_carries_the_renewal_call_to_action(
        self,
        client,
        mongoDatabase,
    ):
        registration = expiringHolder(client, mongoDatabase)
        expiryDate = registration["validUntil"][:10]

        notification = fetchNotifications(client).json()["notifications"][0]

        assert notification["title"] == "Your badge expires in 29 days"
        assert notification["actionLabel"] == "Renew badge"
        assert notification["actionUrl"] == (
            f"http://127.0.0.1:8000/users/{HOLDER_ID}/badge-renewals"
        )
        assert registration["badge"]["badgeCode"] in notification["body"]
        assert "in 29 days" in notification["body"]
        assert expiryDate in notification["body"]
        assert "Request a renewal" in notification["body"]

    def test_action_url_follows_the_configured_base_url(
        self,
        client,
        mongoDatabase,
        monkeypatch,
    ):
        monkeypatch.setenv(
            "BADGE_TRACKING_VERIFICATION_BASE_URL",
            "https://badges.utn.ac.cr/",
        )
        expiringHolder(client, mongoDatabase)

        notification = fetchNotifications(client).json()["notifications"][0]

        assert notification["actionUrl"] == (
            f"https://badges.utn.ac.cr/users/{HOLDER_ID}/badge-renewals"
        )

    @pytest.mark.parametrize(
        ("offset", "expectedCount"),
        [
            ({"days": 30}, 1),
            ({"days": 30, "hours": 1}, 0),
        ],
    )
    def test_the_window_opens_thirty_days_before_expiry(
        self,
        client,
        mongoDatabase,
        offset,
        expectedCount,
    ):
        registration = createHolder(client)
        moveExpiry(mongoDatabase, registration["badge"]["id"], **offset)

        response = fetchNotifications(client)

        assert response.status_code == 200
        assert len(response.json()["notifications"]) == expectedCount

    @pytest.mark.parametrize(
        ("days", "expectedTitle"),
        [
            (30, "Your badge expires in 30 days"),
            (1, "Your badge expires in 1 day"),
        ],
    )
    def test_the_countdown_reads_naturally(
        self,
        client,
        mongoDatabase,
        days,
        expectedTitle,
    ):
        expiringHolder(client, mongoDatabase, days=days)

        notification = fetchNotifications(client).json()["notifications"][0]

        assert notification["title"] == expectedTitle

    def test_the_countdown_is_recomputed_when_the_device_syncs(
        self,
        client,
        mongoDatabase,
    ):
        from jobs.expiry_notifications import scanForExpiringBadges

        registration = createHolder(client)
        moveExpiry(mongoDatabase, registration["badge"]["id"], days=20)
        # The warning was queued ten days ago, when expiry was 30 days away.
        scanForExpiringBadges(datetime.now(timezone.utc) - timedelta(days=10))

        notification = fetchNotifications(client).json()["notifications"][0]

        assert notification["daysUntilExpiry"] == 20
        assert notification["title"] == "Your badge expires in 20 days"

    def test_a_lapsed_badge_reports_the_expiry_instead_of_a_countdown(
        self,
        client,
        mongoDatabase,
    ):
        from jobs.expiry_notifications import scanForExpiringBadges

        registration = createHolder(client)
        validUntil = moveExpiry(mongoDatabase, registration["badge"]["id"], days=-2)
        scanForExpiringBadges(datetime.now(timezone.utc) - timedelta(days=10))

        notification = fetchNotifications(client).json()["notifications"][0]

        assert notification["expired"] is True
        assert notification["daysUntilExpiry"] == 0
        assert notification["title"] == "Your badge has expired"
        assert "expired on" in notification["body"]
        assert validUntil[:10] in notification["body"]

    def test_an_already_expired_badge_raises_no_new_notification(
        self,
        client,
        mongoDatabase,
    ):
        registration = createHolder(client)
        moveExpiry(mongoDatabase, registration["badge"]["id"], days=-1)

        response = fetchNotifications(client)

        assert response.status_code == 200
        assert response.json()["notifications"] == []

    def test_a_holder_is_warned_only_once_per_badge(
        self,
        client,
        mongoDatabase,
    ):
        expiringHolder(client, mongoDatabase)

        first = fetchNotifications(client).json()["notifications"]
        second = fetchNotifications(client).json()["notifications"]

        assert len(second) == 1
        assert second[0]["notificationId"] == first[0]["notificationId"]
        assert second[0]["createdAt"] == first[0]["createdAt"]
        assert mongoDatabase.badge_notifications.count_documents({}) == 1

    def test_a_legacy_badge_without_an_expiry_uses_the_default_validity(
        self,
        client,
        mongoDatabase,
    ):
        registration = createHolder(client)
        issuedAt = (datetime.now(timezone.utc) - timedelta(days=340)).isoformat()
        mongoDatabase.badges.update_one(
            {"id": registration["badge"]["id"]},
            {
                "$set": {"issued_at": issuedAt, "valid_from": issuedAt},
                "$unset": {"valid_until": ""},
            },
        )

        response = fetchNotifications(client)

        assert response.status_code == 200
        notification = response.json()["notifications"][0]
        assert notification["daysUntilExpiry"] == 25

    @pytest.mark.parametrize(
        ("configuredDays", "expectedCount"),
        [
            ("60", 1),
            ("10", 0),
            ("not-a-number", 0),
            ("0", 0),
            ("", 0),
        ],
    )
    def test_the_notice_window_is_configurable(
        self,
        client,
        mongoDatabase,
        monkeypatch,
        configuredDays,
        expectedCount,
    ):
        monkeypatch.setenv("BADGE_TRACKING_EXPIRY_NOTICE_DAYS", configuredDays)
        registration = createHolder(client)
        moveExpiry(mongoDatabase, registration["badge"]["id"], days=45)

        response = fetchNotifications(client)

        assert response.status_code == 200
        assert len(response.json()["notifications"]) == expectedCount

    def test_notifications_stay_with_their_own_holder(
        self,
        client,
        mongoDatabase,
    ):
        expiringHolder(client, mongoDatabase)
        other = createHolder(
            client,
            OTHER_HOLDER_ID,
            fullName="Ana Vargas",
            email="ana.vargas@utn.ac.cr",
            pin=OTHER_HOLDER_PIN,
        )
        moveExpiry(mongoDatabase, other["badge"]["id"], days=5)

        holderNotifications = fetchNotifications(client).json()["notifications"]
        otherNotifications = fetchNotifications(
            client,
            OTHER_HOLDER_ID,
            OTHER_HOLDER_PIN,
        ).json()["notifications"]

        assert len(holderNotifications) == 1
        assert len(otherNotifications) == 1
        assert holderNotifications[0]["badgeId"] != otherNotifications[0]["badgeId"]
        assert otherNotifications[0]["actionUrl"].endswith(
            f"/users/{OTHER_HOLDER_ID}/badge-renewals"
        )


class TestNotificationDelivery:
    def test_acknowledging_marks_the_notice_as_delivered(
        self,
        client,
        mongoDatabase,
    ):
        expiringHolder(client, mongoDatabase)
        notification = fetchNotifications(client).json()["notifications"][0]

        response = acknowledgeNotification(client, notification["notificationId"])

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "delivered"
        assertAwareIsoTimestamp(body["deliveredAt"])
        assert fetchNotifications(client).json()["notifications"] == []

    def test_acknowledging_twice_keeps_the_first_delivery_time(
        self,
        client,
        mongoDatabase,
    ):
        expiringHolder(client, mongoDatabase)
        notificationId = fetchNotifications(client).json()["notifications"][0][
            "notificationId"
        ]
        first = acknowledgeNotification(client, notificationId).json()

        second = acknowledgeNotification(client, notificationId)

        assert second.status_code == 200
        assert second.json()["status"] == "delivered"
        assert second.json()["deliveredAt"] == first["deliveredAt"]

    def test_dismissing_stops_the_notice_from_coming_back(
        self,
        client,
        mongoDatabase,
    ):
        expiringHolder(client, mongoDatabase)
        notificationId = fetchNotifications(client).json()["notifications"][0][
            "notificationId"
        ]

        response = dismissNotification(client, notificationId)

        assert response.status_code == 200
        assert response.json()["status"] == "dismissed"
        assert fetchNotifications(client).json()["notifications"] == []
        assert mongoDatabase.badge_notifications.count_documents({}) == 1

    def test_a_delivered_notice_can_still_be_dismissed(
        self,
        client,
        mongoDatabase,
    ):
        expiringHolder(client, mongoDatabase)
        notificationId = fetchNotifications(client).json()["notifications"][0][
            "notificationId"
        ]
        assert acknowledgeNotification(client, notificationId).status_code == 200

        response = dismissNotification(client, notificationId)

        assert response.status_code == 200
        assert response.json()["status"] == "dismissed"

    def test_dismissing_twice_is_safe(self, client, mongoDatabase):
        expiringHolder(client, mongoDatabase)
        notificationId = fetchNotifications(client).json()["notifications"][0][
            "notificationId"
        ]
        first = dismissNotification(client, notificationId).json()

        second = dismissNotification(client, notificationId)

        assert second.status_code == 200
        assert second.json()["status"] == "dismissed"
        assert second.json()["notificationId"] == first["notificationId"]

    def test_an_unknown_notification_is_not_found(self, client, mongoDatabase):
        expiringHolder(client, mongoDatabase)

        response = acknowledgeNotification(client, "0" * 32)

        assert response.status_code == 404

    def test_a_holder_cannot_touch_another_holders_notification(
        self,
        client,
        mongoDatabase,
    ):
        expiringHolder(client, mongoDatabase)
        createHolder(
            client,
            OTHER_HOLDER_ID,
            fullName="Ana Vargas",
            email="ana.vargas@utn.ac.cr",
            pin=OTHER_HOLDER_PIN,
        )
        notificationId = fetchNotifications(client).json()["notifications"][0][
            "notificationId"
        ]

        response = dismissNotification(
            client,
            notificationId,
            OTHER_HOLDER_ID,
            OTHER_HOLDER_PIN,
        )

        assert response.status_code == 404


class TestNotificationAuthentication:
    def test_fetching_rejects_an_invalid_pin(self, client, mongoDatabase):
        expiringHolder(client, mongoDatabase)

        response = fetchNotifications(client, HOLDER_ID, "999999")

        assert response.status_code == 401

    def test_fetching_requires_a_pin_to_be_set(self, client):
        registerUser(
            client,
            HOLDER_ID,
            fullName="Kevin Picado",
            email="kevin.picado@utn.ac.cr",
        )

        response = fetchNotifications(client)

        assert response.status_code == 409

    def test_fetching_rejects_an_unknown_holder(self, client):
        response = fetchNotifications(client, "999999999")

        assert response.status_code == 404

    @pytest.mark.parametrize("institutionalId", ["12345", "12345678A"])
    def test_fetching_rejects_a_malformed_institutional_id(
        self,
        client,
        institutionalId,
    ):
        response = fetchNotifications(client, institutionalId)

        assert response.status_code == 422

    @pytest.mark.parametrize("pin", ["12345", "abcdef"])
    def test_endpoints_validate_the_pin_format(self, client, pin):
        createHolder(client)

        assert fetchNotifications(client, HOLDER_ID, pin).status_code == 422
        assert requestRenewal(client, HOLDER_ID, pin).status_code == 422


class TestRenewalRequest:
    def test_the_call_to_action_records_a_renewal_request(
        self,
        client,
        mongoDatabase,
    ):
        registration = expiringHolder(client, mongoDatabase)
        fetchNotifications(client)

        response = requestRenewal(client)

        assert response.status_code == 201
        body = response.json()
        assert len(body["requestId"]) == 32
        assert body["badgeId"] == registration["badge"]["id"]
        assert body["badgeCode"] == registration["badge"]["badgeCode"]
        assert body["status"] == "requested"
        assert body["validUntil"] == registration["validUntil"]
        assert body["daysUntilExpiry"] == 29
        assert body["fulfilledAt"] is None
        assert body["fulfilledBadgeId"] is None
        assertAwareIsoTimestamp(body["requestedAt"])

    def test_requesting_a_renewal_clears_the_notification(
        self,
        client,
        mongoDatabase,
    ):
        expiringHolder(client, mongoDatabase)
        notificationId = fetchNotifications(client).json()["notifications"][0][
            "notificationId"
        ]

        assert requestRenewal(client).status_code == 201

        assert fetchNotifications(client).json()["notifications"] == []
        notification = mongoDatabase.badge_notifications.find_one(
            {"notification_id": notificationId}
        )
        assert notification["status"] == "dismissed"
        assert notification["dismissal_reason"] == (
            "Renewal requested by the badge holder"
        )

    def test_tapping_the_call_to_action_twice_reuses_the_open_request(
        self,
        client,
        mongoDatabase,
    ):
        expiringHolder(client, mongoDatabase)
        first = requestRenewal(client).json()

        second = requestRenewal(client)

        assert second.status_code == 201
        assert second.json()["requestId"] == first["requestId"]
        assert second.json()["requestedAt"] == first["requestedAt"]
        assert mongoDatabase.badge_renewal_requests.count_documents({}) == 1

    def test_a_renewal_can_be_requested_after_the_badge_lapsed(
        self,
        client,
        mongoDatabase,
    ):
        registration = expiringHolder(client, mongoDatabase)
        moveExpiry(mongoDatabase, registration["badge"]["id"], days=-3)

        response = requestRenewal(client)

        assert response.status_code == 201
        assert response.json()["status"] == "requested"
        assert response.json()["daysUntilExpiry"] == 0

    def test_a_holder_without_an_active_badge_cannot_request_a_renewal(
        self,
        client,
        mongoDatabase,
    ):
        createAdmin(client)
        holder = expiringHolder(client, mongoDatabase)
        assert updateBadgeStatus(
            client,
            holder["badge"]["id"],
            "revoked",
        ).status_code == 200

        response = requestRenewal(client)

        assert response.status_code == 409

    def test_issuing_a_new_badge_fulfils_the_request(self, client, mongoDatabase):
        createAdmin(client)
        holder = expiringHolder(client, mongoDatabase)
        renewalRequest = requestRenewal(client).json()

        issued = issueBadge(client)

        assert issued.status_code == 201
        newBadgeId = issued.json()["badge"]["id"]
        storedRequest = mongoDatabase.badge_renewal_requests.find_one(
            {"request_id": renewalRequest["requestId"]}
        )
        assert storedRequest["status"] == "fulfilled"
        assert storedRequest["fulfilled_badge_id"] == newBadgeId
        assert storedRequest["badge_id"] == holder["badge"]["id"]
        assertAwareIsoTimestamp(storedRequest["fulfilled_at"])

    def test_a_renewed_badge_starts_a_fresh_renewal_cycle(
        self,
        client,
        mongoDatabase,
    ):
        createAdmin(client)
        expiringHolder(client, mongoDatabase)
        requestRenewal(client)
        newBadge = issueBadge(client).json()["badge"]

        assert fetchNotifications(client).json()["notifications"] == []
        moveExpiry(mongoDatabase, newBadge["id"], days=12)
        response = fetchNotifications(client)

        assert response.status_code == 200
        notification = response.json()["notifications"][0]
        assert notification["badgeId"] == newBadge["id"]
        assert notification["daysUntilExpiry"] == 12


class TestNotificationsFollowTheBadgeLifecycle:
    def test_a_replaced_badge_stops_nagging_the_holder(
        self,
        client,
        mongoDatabase,
    ):
        createAdmin(client)
        holder = expiringHolder(client, mongoDatabase)
        notificationId = fetchNotifications(client).json()["notifications"][0][
            "notificationId"
        ]

        assert issueBadge(client).status_code == 201

        assert fetchNotifications(client).json()["notifications"] == []
        notification = mongoDatabase.badge_notifications.find_one(
            {"notification_id": notificationId}
        )
        assert notification["status"] == "resolved"
        assert notification["badge_id"] == holder["badge"]["id"]
        assertAwareIsoTimestamp(notification["resolved_at"])

    @pytest.mark.parametrize("lifecycleStatus", ["suspended", "revoked"])
    def test_suspension_or_revocation_closes_the_notice_and_request(
        self,
        client,
        mongoDatabase,
        lifecycleStatus,
    ):
        createAdmin(client)
        holder = expiringHolder(client, mongoDatabase)
        notificationId = fetchNotifications(client).json()["notifications"][0][
            "notificationId"
        ]
        renewalRequest = requestRenewal(client).json()

        response = updateBadgeStatus(
            client,
            holder["badge"]["id"],
            lifecycleStatus,
        )

        assert response.status_code == 200
        notification = mongoDatabase.badge_notifications.find_one(
            {"notification_id": notificationId}
        )
        assert notification["status"] in {"dismissed", "resolved"}
        storedRequest = mongoDatabase.badge_renewal_requests.find_one(
            {"request_id": renewalRequest["requestId"]}
        )
        assert storedRequest["status"] == "cancelled"
        assert storedRequest["cancellation_reason"] == "Graduation completed"
        assertAwareIsoTimestamp(storedRequest["cancelled_at"])

    @pytest.mark.parametrize("lifecycleStatus", ["suspended", "revoked"])
    def test_an_inactive_badge_is_never_warned_about(
        self,
        client,
        mongoDatabase,
        lifecycleStatus,
    ):
        createAdmin(client)
        holder = expiringHolder(client, mongoDatabase)
        assert updateBadgeStatus(
            client,
            holder["badge"]["id"],
            lifecycleStatus,
        ).status_code == 200

        response = fetchNotifications(client)

        assert response.status_code == 200
        assert response.json()["notifications"] == []
        assert mongoDatabase.badge_notifications.count_documents({}) == 0

    def test_a_delivered_notice_is_resolved_when_the_badge_is_revoked(
        self,
        client,
        mongoDatabase,
    ):
        createAdmin(client)
        holder = expiringHolder(client, mongoDatabase)
        notificationId = fetchNotifications(client).json()["notifications"][0][
            "notificationId"
        ]
        assert acknowledgeNotification(client, notificationId).status_code == 200

        assert updateBadgeStatus(
            client,
            holder["badge"]["id"],
            "revoked",
        ).status_code == 200

        notification = mongoDatabase.badge_notifications.find_one(
            {"notification_id": notificationId}
        )
        assert notification["status"] == "resolved"
        assert notification["resolution_reason"] == "Graduation completed"


class TestScheduledExpiryScan:
    def test_the_scan_warns_holders_who_never_opened_the_app(
        self,
        client,
        mongoDatabase,
    ):
        from jobs.expiry_notifications import scanForExpiringBadges

        registration = createHolder(client)
        moveExpiry(mongoDatabase, registration["badge"]["id"], days=7)
        other = createHolder(
            client,
            OTHER_HOLDER_ID,
            fullName="Ana Vargas",
            email="ana.vargas@utn.ac.cr",
            pin=OTHER_HOLDER_PIN,
        )

        summary = scanForExpiringBadges()

        assert summary == {"scanned": 1, "queued": 1}
        notification = mongoDatabase.badge_notifications.find_one(
            {"user_id": registration["user"]["id"]}
        )
        assert notification["status"] == "pending"
        assert notification["badge_id"] == registration["badge"]["id"]
        assert notification["notice_days"] == 30
        assert mongoDatabase.badge_notifications.count_documents(
            {"user_id": other["user"]["id"]}
        ) == 0

    def test_running_the_scan_again_warns_nobody_twice(
        self,
        client,
        mongoDatabase,
    ):
        from jobs.expiry_notifications import scanForExpiringBadges

        registration = createHolder(client)
        moveExpiry(mongoDatabase, registration["badge"]["id"], days=7)
        scanForExpiringBadges()

        summary = scanForExpiringBadges()

        assert summary == {"scanned": 1, "queued": 0}
        assert mongoDatabase.badge_notifications.count_documents({}) == 1

    def test_the_scan_skips_deactivated_identities(self, client, mongoDatabase):
        from jobs.expiry_notifications import scanForExpiringBadges

        registration = createHolder(client)
        moveExpiry(mongoDatabase, registration["badge"]["id"], days=7)
        mongoDatabase.users.update_one(
            {"id": registration["user"]["id"]},
            {"$set": {"is_active": False}},
        )

        summary = scanForExpiringBadges()

        assert summary == {"scanned": 0, "queued": 0}
        assert mongoDatabase.badge_notifications.count_documents({}) == 0

    def test_the_scan_ignores_badges_outside_the_window(
        self,
        client,
        mongoDatabase,
    ):
        from jobs.expiry_notifications import scanForExpiringBadges

        registration = createHolder(client)
        moveExpiry(mongoDatabase, registration["badge"]["id"], days=90)

        summary = scanForExpiringBadges()

        assert summary == {"scanned": 0, "queued": 0}
        assert mongoDatabase.badge_notifications.count_documents({}) == 0

    def test_a_scanned_notification_reaches_the_device_unchanged(
        self,
        client,
        mongoDatabase,
    ):
        from jobs.expiry_notifications import scanForExpiringBadges

        registration = createHolder(client)
        moveExpiry(mongoDatabase, registration["badge"]["id"], days=7)
        scanForExpiringBadges()

        response = fetchNotifications(client)

        assert response.status_code == 200
        notification = response.json()["notifications"][0]
        assert notification["daysUntilExpiry"] == 7
        assert notification["actionLabel"] == "Renew badge"
        assert mongoDatabase.badge_notifications.count_documents({}) == 1
