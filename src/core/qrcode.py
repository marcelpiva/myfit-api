"""QR Code generation utilities."""
import base64
import io
import logging

logger = logging.getLogger(__name__)


def generate_qr_code_base64(
    data: str,
    box_size: int = 10,
    border: int = 2,
    fill_color: str = "#000000",
    back_color: str = "#FFFFFF",
) -> str | None:
    """Generate a QR code and return it as a base64 data URL.

    Args:
        data: The data to encode in the QR code
        box_size: Size of each box in the QR code
        border: Border size around the QR code
        fill_color: Color of the QR code pattern
        back_color: Background color

    Returns:
        Base64 data URL string (data:image/png;base64,...) or None if generation fails
    """
    try:
        import qrcode
        from qrcode.constants import ERROR_CORRECT_H

        # Create QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=ERROR_CORRECT_H,
            box_size=box_size,
            border=border,
        )
        qr.add_data(data)
        qr.make(fit=True)

        # Create image
        img = qr.make_image(fill_color=fill_color, back_color=back_color)

        # Convert to base64
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)

        base64_data = base64.b64encode(buffer.read()).decode("utf-8")
        return f"data:image/png;base64,{base64_data}"

    except ImportError:
        logger.warning("qrcode library not installed. QR code generation unavailable.")
        return None
    except (ValueError, OSError) as e:
        logger.error(f"Error generating QR code: {e}")
        return None


def generate_invite_qr_code(invite_url: str) -> str | None:
    """Generate a QR code for an invite URL.

    Uses MyFit brand colors for the QR code.

    Args:
        invite_url: The URL to encode

    Returns:
        Base64 data URL string or None if generation fails
    """
    return generate_qr_code_base64(
        data=invite_url,
        box_size=10,
        border=2,
        fill_color="#1a1a2e",  # MyFit dark color
        back_color="#FFFFFF",
    )
