"""Colour and logo rules shared by the institutional branding endpoints."""

import re


HEX_COLOR_PATTERN = re.compile(r"^#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$")

MAX_LOGO_SIZE_IN_BYTES = 512 * 1024

# Raster formats only. An SVG can carry script, and the logo is served back
# from the API origin, so accepting one would hand every badge viewer a stored
# cross-site scripting vector.
SUPPORTED_LOGO_CONTENT_TYPES = ("image/png", "image/jpeg", "image/webp")

# Text stays readable on a light accent below this relative luminance.
_LIGHT_BACKGROUND_LUMINANCE = 0.179


def normalizeHexColor(value: str) -> str:
    """Return an accent colour as #RRGGBB, expanding the #RGB shorthand."""
    cleanedValue = value.strip()

    if not HEX_COLOR_PATTERN.match(cleanedValue):
        raise ValueError(
            "Accent colours must be hex values such as #1F3B73 or #1B7"
        )

    colorDigits = cleanedValue[1:]
    if len(colorDigits) == 3:
        colorDigits = "".join(digit * 2 for digit in colorDigits)

    return f"#{colorDigits.upper()}"


def _channelLuminance(channel: float) -> float:
    if channel <= 0.03928:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def relativeLuminance(hexColor: str) -> float:
    colorDigits = normalizeHexColor(hexColor)[1:]
    channels = (
        int(colorDigits[position : position + 2], 16) / 255
        for position in (0, 2, 4)
    )
    red, green, blue = (_channelLuminance(channel) for channel in channels)

    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrastTextColor(hexColor: str) -> str:
    """Return the black or white that stays legible on an accent colour."""
    if relativeLuminance(hexColor) > _LIGHT_BACKGROUND_LUMINANCE:
        return "#000000"
    return "#FFFFFF"


def detectImageContentType(content: bytes) -> str | None:
    """Identify a logo from its own bytes, ignoring what the client declared."""
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"

    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"

    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"

    return None
