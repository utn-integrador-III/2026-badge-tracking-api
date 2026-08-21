def test_initialize_database_creates_required_indexes(mongoDatabase):
    userIndexes = mongoDatabase.users.index_information()
    badgeIndexes = mongoDatabase.badges.index_information()
    deliveryIndexes = mongoDatabase.badge_deliveries.index_information()

    assert "unique_user_email" in userIndexes
    assert userIndexes["unique_user_email"]["unique"] is True
    assert "unique_user_institutional_id" in userIndexes
    assert userIndexes["unique_user_institutional_id"]["unique"] is True
    assert "unique_badge_code" in badgeIndexes
    assert badgeIndexes["unique_badge_code"]["unique"] is True

    # Reissuing gives a user several badges over time, so user_id is indexed
    # for lookups but is deliberately not unique.
    assert "badge_user_status" in badgeIndexes
    assert badgeIndexes["badge_user_status"].get("unique") is None
    assert "unique_badge_user_id" not in badgeIndexes
    assert "badge_delivery_badge_status" in deliveryIndexes

    notificationIndexes = mongoDatabase.badge_notifications.index_information()
    renewalIndexes = mongoDatabase.badge_renewal_requests.index_information()

    # A badge is warned about once, and only one renewal request of a badge
    # can be open at a time.
    assert "unique_badge_notification_per_badge" in notificationIndexes
    assert notificationIndexes["unique_badge_notification_per_badge"]["unique"] is True
    assert "badge_notification_user_status" in notificationIndexes
    assert "unique_badge_renewal_request_per_badge_status" in renewalIndexes
    assert (
        renewalIndexes["unique_badge_renewal_request_per_badge_status"]["unique"]
        is True
    )
