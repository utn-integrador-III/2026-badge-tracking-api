def test_initialize_database_creates_required_indexes(mongoDatabase):
    userIndexes = mongoDatabase.users.index_information()
    badgeIndexes = mongoDatabase.badges.index_information()

    assert "unique_user_email" in userIndexes
    assert userIndexes["unique_user_email"]["unique"] is True
    assert "unique_user_institutional_id" in userIndexes
    assert userIndexes["unique_user_institutional_id"]["unique"] is True
    assert "unique_badge_user_id" in badgeIndexes
    assert badgeIndexes["unique_badge_user_id"]["unique"] is True
    assert "unique_badge_code" in badgeIndexes
    assert badgeIndexes["unique_badge_code"]["unique"] is True
