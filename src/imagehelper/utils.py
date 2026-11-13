from __future__ import annotations

# stdlib
import base64
import hashlib
from io import BytesIO
import logging
import os
from typing import Dict
from typing import Protocol
from typing import TYPE_CHECKING

# pypi
from PIL import Image
from PIL import ImageSequence

if TYPE_CHECKING:
    from typing_extensions import Buffer

# local
from . import _io

# ==============================================================================

log = logging.getLogger(__name__)

# ------------------------------------------------------------------------------


class ImageErrorCodes(object):
    """Consolidating codes and error messages"""

    INVALID_FILETYPE = 1
    INVALID_OTHER = 2
    NO_IMAGE = 3
    MISSING_FILE = 4
    UNSUPPORTED_IMAGE_CLASS = 5  # Must be cgi.FieldStorage or file
    INVALID_REBUILD = 6
    MISSING_FILENAME_METHOD = 7


_PIL_type_to_content_type: Dict[str, str] = {
    "gif": "image/gif",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "pdf": "application/pdf",
    "png": "image/png",
}

_PIL_type_to_standardized: Dict[str, str] = {
    "gif": "gif",
    "jpg": "jpg",
    "jpeg": "jpg",
    "pdf": "pdf",
    "png": "png",
}

_standardized_to_PIL_type: Dict[str, str] = {
    "gif": "GIF",
    "jpg": "JPEG",
    "jpeg": "JPEG",
    "pdf": "PDF",
    "png": "PNG",
}


# ==============================================================================


class _Seekable(Protocol):
    """A stream whose position can be queried and moved."""

    def seek(self, offset: int, whence: int = 0, /) -> int: ...
    def tell(self) -> int: ...


class _BinaryStream(_Seekable, Protocol):
    """A seekable stream that reads bytes."""

    def read(self, size: int = -1, /) -> bytes: ...


def is_image_animated(im: Image.Image) -> bool:
    """Check for a second frame and leave the image on it if present."""
    im.seek(0)
    try:
        im.seek(1)
        return True
    except EOFError:
        return False


def animated_image_totalframes(im: Image.Image) -> int:
    """Count frames from the start, leaving the image on the last frame."""
    im.seek(0)
    _frame = 0
    for frame in ImageSequence.Iterator(im):
        _frame = _frame + 1
    return _frame


def derive_format(intended_format: str, original_format: str) -> str:
    """Return the requested format in uppercase.

    AUTO and ORIGINAL select PNG for PNG or GIF input and JPEG otherwise.
    """
    intended_format = intended_format.upper()
    if intended_format in ("AUTO", "ORIGINAL"):
        _og_format = original_format.upper()
        if _og_format in ("PNG", "GIF"):
            intended_format = "PNG"
        else:
            intended_format = "JPEG"
    return intended_format


def PIL_type_to_content_type(ctype: str) -> str:
    """Return the MIME type for a Pillow format or raise ValueError."""
    ctype = ctype.lower()
    if ctype in _PIL_type_to_content_type:
        return _PIL_type_to_content_type[ctype]
    raise ValueError("invalid ctype")


def PIL_type_to_standardized(ctype: str) -> str:
    """Return the normalized lowercase format name or raise ValueError."""
    ctype = ctype.lower()
    if ctype in _PIL_type_to_standardized:
        return _PIL_type_to_standardized[ctype]
    raise ValueError("invalid ctype - `%s`" % ctype)


def PIL_type_to_extension(ctype: str) -> str:
    """Return the lowercase file extension without a dot or raise ValueError."""
    ctype = ctype.lower()
    if ctype in _PIL_type_to_standardized:
        return _PIL_type_to_standardized[ctype]
    raise ValueError("invalid ctype")


def standardized_to_PIL_type(ctype: str) -> str:
    """Return the Pillow format for a normalized name or raise ValueError."""
    ctype = ctype.lower()
    if ctype in _standardized_to_PIL_type:
        return _standardized_to_PIL_type[ctype]
    raise ValueError("invalid ctype")


def file_size(fileobj: _Seekable) -> int:
    """Return the stream's size and leave its position at the start."""
    fileobj.seek(0, os.SEEK_END)
    sized = fileobj.tell()
    fileobj.seek(0)
    return sized


def file_md5(fileobj: _BinaryStream) -> str:
    """Hash the entire stream and rewind it before returning the MD5 hex digest."""
    fileobj.seek(0)
    md5 = hashlib.md5()
    block_size = md5.block_size * 128
    for chunk in iter(lambda: fileobj.read(block_size), b""):
        md5.update(chunk)
    fileobj.seek(0)
    return md5.hexdigest()


def file_b64(fileobj: _BinaryStream) -> bytes:
    """Encode the entire stream as Base64 with line breaks, then rewind it."""
    fileobj.seek(0)
    as_b64 = base64.encodebytes(fileobj.read())
    fileobj.seek(0)
    return as_b64


def b64_decode_to_file(coded_string: str | Buffer) -> BytesIO:
    """Decode Base64 into a rewound stream, propagating decoding errors."""
    decoded_data = base64.b64decode(coded_string)
    fileobj = _io._FilelikePreference()
    fileobj.write(decoded_data)
    fileobj.seek(0)
    return fileobj
