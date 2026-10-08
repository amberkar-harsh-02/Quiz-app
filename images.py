"""Cleans up images professors attach to questions before they are stored."""
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
# Plenty for a projector; keeps a typical stored image to a few hundred KB
MAX_SIDE = 1600
ALLOWED_FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png"}


def clean_image(raw: bytes) -> tuple[bytes, str, int, int]:
    """Returns (data, content_type, width, height) for a JPG or PNG, or raises ValueError.

    The format is read from the file's contents, not its name. The image is re-saved, which
    drops EXIF data such as a phone photo's GPS location, and shrunk to fit MAX_SIDE.
    """
    try:
        with Image.open(BytesIO(raw)) as probe:
            fmt = probe.format
            probe.verify()
        if fmt not in ALLOWED_FORMATS:
            raise ValueError
        img = Image.open(BytesIO(raw))
        img.load()
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError, ValueError):
        raise ValueError("Only JPG and PNG images are allowed.")

    # Phones store "rotate me" in EXIF; apply it before EXIF is dropped
    img = ImageOps.exif_transpose(img)
    img.thumbnail((MAX_SIDE, MAX_SIDE))

    out = BytesIO()
    if fmt == "PNG":
        # PNG stays PNG so diagrams keep sharp edges and transparency
        img.save(out, "PNG", optimize=True)
    else:
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.save(out, "JPEG", quality=85, optimize=True)
    return out.getvalue(), ALLOWED_FORMATS[fmt], img.width, img.height
