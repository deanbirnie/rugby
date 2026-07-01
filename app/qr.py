import io

import qrcode


def generate_qr_png(data: str, box_size: int = 10) -> bytes:
    img = qrcode.make(data, border=2, box_size=box_size)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
