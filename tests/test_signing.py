import pytest

from utils.signing import (
    SigningConfigurationError,
    getSigningKey,
    readSignedPayload,
    signPayload,
)


TEST_SIGNING_KEY = "test-only-signing-key-with-at-least-32-bytes"


def test_signing_key_is_required(monkeypatch):
    monkeypatch.delenv("BADGE_TRACKING_SIGNING_KEY", raising=False)

    with pytest.raises(
        SigningConfigurationError,
        match="must be configured",
    ):
        getSigningKey()


def test_signing_key_requires_at_least_32_bytes(monkeypatch):
    monkeypatch.setenv("BADGE_TRACKING_SIGNING_KEY", "too-short")

    with pytest.raises(
        SigningConfigurationError,
        match="at least 32 bytes",
    ):
        getSigningKey()


@pytest.mark.parametrize(
    "configuredKey",
    [
        " " * 32,
        "development-only-badge-signing-key",
        "replace-with-a-random-secret-of-at-least-32-bytes",
    ],
)
def test_signing_key_rejects_blank_and_known_values(monkeypatch, configuredKey):
    monkeypatch.setenv("BADGE_TRACKING_SIGNING_KEY", configuredKey)

    with pytest.raises(SigningConfigurationError):
        getSigningKey()


def test_signing_key_rejects_surrounding_whitespace(monkeypatch):
    monkeypatch.setenv(
        "BADGE_TRACKING_SIGNING_KEY",
        f" {TEST_SIGNING_KEY} ",
    )

    with pytest.raises(
        SigningConfigurationError,
        match="surrounding whitespace",
    ):
        getSigningKey()


def test_signed_payload_round_trip(monkeypatch):
    monkeypatch.setenv("BADGE_TRACKING_SIGNING_KEY", TEST_SIGNING_KEY)
    payload = {"v": 1, "message": "verified"}

    token = signPayload(payload)

    assert readSignedPayload(token) == payload
