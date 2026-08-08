import base64
from io import BytesIO

import qrcode


def buildQrCodeDataUri(payload: str) -> str:
    qrCode = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qrCode.add_data(payload)
    qrCode.make(fit=True)

    buffer = BytesIO()
    qrCode.make_image(fill_color="black", back_color="white").save(buffer, format="PNG")
    encodedImage = base64.b64encode(buffer.getvalue()).decode()

    return f"data:image/png;base64,{encodedImage}"
