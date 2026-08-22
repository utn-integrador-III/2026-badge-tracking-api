from datetime import datetime
from io import BytesIO

import pytest
from PIL import Image


ADMIN_ID = "900000001"
ADMIN_PIN = "481726"
HOLDER_ID = "123456789"
HOLDER_PIN = "281992"
OTHER_ADMIN_ID = "900000002"
OTHER_ADMIN_PIN = "573914"
OTHER_HOLDER_ID = "222222222"

DEFAULT_INSTITUTION = "Universidad Técnica Nacional"
OTHER_INSTITUTION = "Universidad de Costa Rica"
DEFAULT_PRIMARY_COLOR = "#1F3B73"
DEFAULT_SECONDARY_COLOR = "#C8A227"

UNBRANDED_PALETTE = {
    "primaryColor": DEFAULT_PRIMARY_COLOR,
    "secondaryColor": DEFAULT_SECONDARY_COLOR,
    "contrastTextColor": "#FFFFFF",
    "logoUrl": None,
    "logoContentType": None,
    "logoSizeInBytes": None,
    "logoUpdatedAt": None,
    "isCustomized": False,
    "updatedAt": None,
}

SVG_LOGO = b'<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>'


def buildImage(imageFormat: str = "PNG") -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (8, 8), (31, 59, 115)).save(buffer, format=imageFormat)
    return buffer.getvalue()


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


def createAdmin(
    client,
    institutionalId: str = ADMIN_ID,
    *,
    email: str = "admin@utn.ac.cr",
    pin: str = ADMIN_PIN,
) -> dict:
    registration = registerUser(
        client,
        institutionalId,
        fullName="Institutional Administrator",
        email=email,
        role="admin",
    )
    setPin(client, institutionalId, pin)
    return registration


def createHolder(
    client,
    institutionalId: str = HOLDER_ID,
    *,
    fullName: str = "Kevin Picado",
    email: str = "kevin.picado@utn.ac.cr",
) -> dict:
    registration = registerUser(
        client,
        institutionalId,
        fullName=fullName,
        email=email,
    )
    setPin(client, institutionalId, HOLDER_PIN)
    return registration


def updateBranding(
    client,
    *,
    logo: bytes | None = None,
    logoName: str = "logo.png",
    logoContentType: str = "image/png",
    primaryColor: str = "#1F3B73",
    secondaryColor: str = "#C8A227",
    adminInstitutionalId: str = ADMIN_ID,
    adminPin: str = ADMIN_PIN,
):
    formFields = {
        "adminInstitutionalId": adminInstitutionalId,
        "adminPin": adminPin,
        "primaryColor": primaryColor,
        "secondaryColor": secondaryColor,
    }
    if logo is None:
        return client.put("/institutions/branding", data=formFields)

    return client.put(
        "/institutions/branding",
        data=formFields,
        files={"logo": (logoName, logo, logoContentType)},
    )


def brandTheInstitution(client, **overrides) -> dict:
    response = updateBranding(client, logo=buildImage(), **overrides)
    assert response.status_code == 200
    return response.json()


def assertAwareIsoTimestamp(value: str) -> None:
    parsedValue = datetime.fromisoformat(value)
    assert parsedValue.tzinfo is not None
    assert parsedValue.utcoffset() is not None


class TestDefaultBranding:
    def test_an_institution_starts_on_the_default_palette(self, client):
        response = client.get("/institutions/branding")

        assert response.status_code == 200
        assert response.json() == {
            "institution": DEFAULT_INSTITUTION,
            **UNBRANDED_PALETTE,
        }

    def test_an_unbranded_badge_still_renders(self, client):
        createHolder(client)

        response = client.get(f"/users/{HOLDER_ID}/badge-profile")

        assert response.status_code == 200
        assert response.json()["branding"] == {
            "institution": DEFAULT_INSTITUTION,
            **UNBRANDED_PALETTE,
        }


class TestUploadingTheBrand:
    def test_admin_uploads_a_logo_and_chooses_accent_colors(
        self,
        client,
        mongoDatabase,
    ):
        admin = createAdmin(client)
        logo = buildImage()

        response = updateBranding(
            client,
            logo=logo,
            primaryColor="#0b5fff",
            secondaryColor="#ffd166",
        )

        assert response.status_code == 200
        body = response.json()
        assert body["institution"] == DEFAULT_INSTITUTION
        assert body["primaryColor"] == "#0B5FFF"
        assert body["secondaryColor"] == "#FFD166"
        assert body["isCustomized"] is True
        assert body["logoContentType"] == "image/png"
        assert body["logoSizeInBytes"] == len(logo)
        assert body["logoUrl"].startswith(
            "http://127.0.0.1:8000/institutions/branding/logos/"
        )
        assertAwareIsoTimestamp(body["logoUpdatedAt"])
        assertAwareIsoTimestamp(body["updatedAt"])

        branding = mongoDatabase.institution_branding.find_one(
            {"institution": DEFAULT_INSTITUTION}
        )
        assert bytes(branding["logo_bytes"]) == logo
        assert branding["updated_by_user_id"] == admin["user"]["id"]

    @pytest.mark.parametrize(
        ("imageFormat", "expectedContentType"),
        [
            ("PNG", "image/png"),
            ("JPEG", "image/jpeg"),
            ("WEBP", "image/webp"),
        ],
    )
    def test_the_supported_logo_formats_are_accepted(
        self,
        client,
        imageFormat,
        expectedContentType,
    ):
        createAdmin(client)

        response = updateBranding(client, logo=buildImage(imageFormat))

        assert response.status_code == 200
        assert response.json()["logoContentType"] == expectedContentType

    def test_the_format_comes_from_the_bytes_not_the_client(self, client):
        createAdmin(client)

        response = updateBranding(
            client,
            logo=buildImage("JPEG"),
            logoName="logo.png",
            logoContentType="image/png",
        )

        assert response.status_code == 200
        assert response.json()["logoContentType"] == "image/jpeg"

    @pytest.mark.parametrize(
        ("primaryColor", "expectedPrimary", "expectedContrast"),
        [
            ("#1b7", "#11BB77", "#000000"),
            ("#1f3b73", "#1F3B73", "#FFFFFF"),
            (" #FFDD00 ", "#FFDD00", "#000000"),
        ],
    )
    def test_accent_colors_are_normalized_with_a_readable_text_color(
        self,
        client,
        primaryColor,
        expectedPrimary,
        expectedContrast,
    ):
        createAdmin(client)

        response = updateBranding(client, primaryColor=primaryColor)

        assert response.status_code == 200
        assert response.json()["primaryColor"] == expectedPrimary
        assert response.json()["contrastTextColor"] == expectedContrast

    def test_colors_can_be_adjusted_without_resending_the_logo(self, client):
        createAdmin(client)
        branded = brandTheInstitution(client)

        response = updateBranding(client, primaryColor="#204020")

        assert response.status_code == 200
        body = response.json()
        assert body["primaryColor"] == "#204020"
        assert body["logoUrl"] == branded["logoUrl"]
        assert body["logoUpdatedAt"] == branded["logoUpdatedAt"]

    def test_replacing_the_logo_retires_the_previous_one(self, client):
        createAdmin(client)
        firstBranding = brandTheInstitution(client)

        secondBranding = brandTheInstitution(client)

        assert secondBranding["logoUrl"] != firstBranding["logoUrl"]
        assert client.get(firstBranding["logoUrl"]).status_code == 404
        assert client.get(secondBranding["logoUrl"]).status_code == 200

    def test_branding_is_stored_once_per_institution(self, client, mongoDatabase):
        createAdmin(client)
        brandTheInstitution(client)

        brandTheInstitution(client, primaryColor="#204020")

        assert mongoDatabase.institution_branding.count_documents({}) == 1


class TestBrandingAuthorization:
    def test_a_badge_holder_cannot_brand_the_institution(self, client):
        createHolder(client)

        response = updateBranding(
            client,
            logo=buildImage(),
            adminInstitutionalId=HOLDER_ID,
            adminPin=HOLDER_PIN,
        )

        assert response.status_code == 403

    @pytest.mark.parametrize("lifecycleStatus", ["suspended", "revoked"])
    def test_an_admin_without_an_active_badge_loses_access(
        self,
        client,
        lifecycleStatus,
    ):
        admin = createAdmin(client)
        createAdmin(
            client,
            OTHER_ADMIN_ID,
            email="second.admin@utn.ac.cr",
            pin=OTHER_ADMIN_PIN,
        )
        lifecycleResponse = client.patch(
            f"/badges/{admin['badge']['id']}/status",
            json={
                "adminInstitutionalId": OTHER_ADMIN_ID,
                "adminPin": OTHER_ADMIN_PIN,
                "status": lifecycleStatus,
                "reason": "Administrator access withdrawn",
            },
        )
        assert lifecycleResponse.status_code == 200

        response = updateBranding(client, logo=buildImage())

        assert response.status_code == 403

    def test_branding_rejects_a_wrong_pin(self, client):
        createAdmin(client)

        response = updateBranding(client, logo=buildImage(), adminPin="999999")

        assert response.status_code == 401

    def test_branding_rejects_an_unknown_admin(self, client):
        response = updateBranding(client, logo=buildImage())

        assert response.status_code == 404

    def test_branding_requires_a_pin_to_be_set(self, client):
        registerUser(
            client,
            ADMIN_ID,
            fullName="Institutional Administrator",
            email="admin@utn.ac.cr",
            role="admin",
        )

        response = updateBranding(client, logo=buildImage())

        assert response.status_code == 409

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("adminInstitutionalId", "12345"),
            ("adminPin", "abcdef"),
            ("primaryColor", "1F3B73"),
            ("primaryColor", "#12"),
            ("secondaryColor", "not-a-color"),
            ("secondaryColor", "#GGGGGG"),
        ],
    )
    def test_branding_validates_the_submitted_form(self, client, field, value):
        createAdmin(client)

        response = updateBranding(client, logo=buildImage(), **{field: value})

        assert response.status_code == 422


class TestLogoValidation:
    def test_an_oversized_logo_is_rejected(self, client):
        from utils.branding import MAX_LOGO_SIZE_IN_BYTES

        createAdmin(client)
        oversizedLogo = buildImage() + b"\x00" * MAX_LOGO_SIZE_IN_BYTES

        response = updateBranding(client, logo=oversizedLogo)

        assert response.status_code == 413

    def test_a_logo_at_the_size_limit_is_accepted(self, client):
        from utils.branding import MAX_LOGO_SIZE_IN_BYTES

        createAdmin(client)
        logo = buildImage()
        paddedLogo = logo + b"\x00" * (MAX_LOGO_SIZE_IN_BYTES - len(logo))

        response = updateBranding(client, logo=paddedLogo)

        assert response.status_code == 200
        assert response.json()["logoSizeInBytes"] == MAX_LOGO_SIZE_IN_BYTES

    @pytest.mark.parametrize(
        ("logo", "logoName", "logoContentType"),
        [
            (SVG_LOGO, "logo.svg", "image/svg+xml"),
            (b"GIF89a still not supported", "logo.gif", "image/gif"),
            (b"%PDF-1.7 not an image at all", "logo.pdf", "application/pdf"),
        ],
    )
    def test_an_unsupported_format_is_rejected(
        self,
        client,
        logo,
        logoName,
        logoContentType,
    ):
        createAdmin(client)

        response = updateBranding(
            client,
            logo=logo,
            logoName=logoName,
            logoContentType=logoContentType,
        )

        assert response.status_code == 415

    def test_an_empty_logo_file_is_rejected(self, client):
        createAdmin(client)

        response = updateBranding(client, logo=b"")

        assert response.status_code == 422

    def test_a_rejected_upload_leaves_the_brand_untouched(
        self,
        client,
        mongoDatabase,
    ):
        createAdmin(client)
        branded = brandTheInstitution(client)

        response = updateBranding(
            client,
            logo=b"%PDF-1.7 not an image at all",
            primaryColor="#204020",
        )

        assert response.status_code == 415
        assert client.get("/institutions/branding").json() == branded
        assert mongoDatabase.institution_branding.count_documents({}) == 1


class TestServingTheLogo:
    def test_the_logo_is_served_back_byte_for_byte(self, client):
        createAdmin(client)
        logo = buildImage()
        branding = updateBranding(client, logo=logo).json()

        response = client.get(branding["logoUrl"])

        assert response.status_code == 200
        assert response.content == logo
        assert response.headers["content-type"] == "image/png"

    def test_the_logo_is_served_with_hardened_headers(self, client):
        createAdmin(client)
        branding = brandTheInstitution(client)

        response = client.get(branding["logoUrl"])

        assert response.status_code == 200
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["content-security-policy"] == (
            "default-src 'none'; sandbox"
        )
        assert "immutable" in response.headers["cache-control"]

    def test_an_unknown_logo_is_not_found(self, client):
        response = client.get("/institutions/branding/logos/" + "0" * 32)

        assert response.status_code == 404


class TestBrandedBadges:
    def test_a_badge_reflects_the_institutional_brand(self, client):
        createAdmin(client)
        createHolder(client)
        branding = brandTheInstitution(
            client,
            primaryColor="#0b5fff",
            secondaryColor="#ffd166",
        )

        response = client.get(f"/users/{HOLDER_ID}/badge-profile")

        assert response.status_code == 200
        assert response.json()["branding"] == branding

    def test_the_credential_details_carry_the_brand_too(self, client):
        createAdmin(client)
        createHolder(client)
        branding = brandTheInstitution(client)

        response = client.post(
            f"/users/{HOLDER_ID}/badge-profile/details",
            json={"pin": HOLDER_PIN},
        )

        assert response.status_code == 200
        assert response.json()["branding"] == branding
        assert response.json()["issuingAuthority"] == branding["institution"]

    def test_a_reissued_badge_keeps_the_brand(self, client):
        createAdmin(client)
        createHolder(client)
        branding = brandTheInstitution(client)

        issued = client.post(
            "/badges",
            json={
                "adminInstitutionalId": ADMIN_ID,
                "adminPin": ADMIN_PIN,
                "institutionalId": HOLDER_ID,
            },
        )

        assert issued.status_code == 201
        profile = client.get(f"/users/{HOLDER_ID}/badge-profile")
        assert profile.json()["branding"] == branding

    def test_each_institution_keeps_its_own_brand(self, client, monkeypatch):
        createAdmin(client)
        createHolder(client)
        brandTheInstitution(client, primaryColor="#0b5fff")

        monkeypatch.setenv("BADGE_TRACKING_ISSUING_AUTHORITY", OTHER_INSTITUTION)
        createHolder(
            client,
            OTHER_HOLDER_ID,
            fullName="Ana Vargas",
            email="ana.vargas@ucr.ac.cr",
        )

        brandedProfile = client.get(f"/users/{HOLDER_ID}/badge-profile").json()
        otherProfile = client.get(f"/users/{OTHER_HOLDER_ID}/badge-profile").json()

        assert brandedProfile["branding"]["primaryColor"] == "#0B5FFF"
        assert otherProfile["branding"] == {
            "institution": OTHER_INSTITUTION,
            **UNBRANDED_PALETTE,
        }

    def test_an_admin_brands_the_institution_that_issued_their_badge(
        self,
        client,
        monkeypatch,
        mongoDatabase,
    ):
        monkeypatch.setenv("BADGE_TRACKING_ISSUING_AUTHORITY", OTHER_INSTITUTION)
        createAdmin(client)
        createHolder(client)

        branding = brandTheInstitution(client, primaryColor="#0b5fff")

        assert branding["institution"] == OTHER_INSTITUTION
        assert mongoDatabase.institution_branding.count_documents(
            {"institution": OTHER_INSTITUTION}
        ) == 1
        profile = client.get(f"/users/{HOLDER_ID}/badge-profile")
        assert profile.json()["branding"]["primaryColor"] == "#0B5FFF"

    def test_the_logo_url_follows_the_configured_base_url(
        self,
        client,
        monkeypatch,
    ):
        monkeypatch.setenv(
            "BADGE_TRACKING_VERIFICATION_BASE_URL",
            "https://badges.utn.ac.cr/",
        )
        createAdmin(client)

        branding = brandTheInstitution(client)

        assert branding["logoUrl"].startswith(
            "https://badges.utn.ac.cr/institutions/branding/logos/"
        )
