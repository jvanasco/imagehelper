# stdlib
import base64
import hashlib
import logging
import os
from typing import Dict

# pypi
from PIL import ImageSequence

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


def is_image_animated(im) -> bool:
    im.seek(0)
    try:
        im.seek(1)
        return True
    except EOFError:
        return False


def animated_image_totalframes(im) -> int:
    im.seek(0)
    _frame = 0
    for frame in ImageSequence.Iterator(im):
        _frame = _frame + 1
    return _frame


def derive_format(intended_format: str, original_format: str) -> str:
    """
    1. returns uppercase
    2. for the special cases of "AUTO" and "ORIGINAL"
       this will parse the original format and possibly change it

    SEE ALSO: imagehelper.saver.utils.derive_resized_format
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
    ctype = ctype.lower()
    if ctype in _PIL_type_to_content_type:
        return _PIL_type_to_content_type[ctype]
    raise ValueError("invalid ctype")


def PIL_type_to_standardized(ctype: str) -> str:
    ctype = ctype.lower()
    if ctype in _PIL_type_to_standardized:
        return _PIL_type_to_standardized[ctype]
    raise ValueError("invalid ctype - `%s`" % ctype)


def PIL_type_to_extension(ctype: str) -> str:
    ctype = ctype.lower()
    if ctype in _PIL_type_to_standardized:
        return _PIL_type_to_standardized[ctype]
    raise ValueError("invalid ctype")


def standardized_to_PIL_type(ctype: str) -> str:
    ctype = ctype.lower()
    if ctype in _standardized_to_PIL_type:
        return _standardized_to_PIL_type[ctype]
    raise ValueError("invalid ctype")


def file_size(fileobj) -> int:
    """what's the size of the object?"""
    fileobj.seek(0, os.SEEK_END)
    sized = fileobj.tell()
    fileobj.seek(0)
    return sized


def file_md5(fileobj) -> str:
    fileobj.seek(0)
    md5 = hashlib.md5()
    block_size = md5.block_size * 128
    for chunk in iter(lambda: fileobj.read(block_size), b""):
        md5.update(chunk)
    fileobj.seek(0)
    return md5.hexdigest()


def file_b64(fileobj) -> bytes:
    fileobj.seek(0)
    as_b64 = base64.encodebytes(fileobj.read())
    fileobj.seek(0)
    return as_b64


def b64_decode_to_file(coded_string):
    decoded_data = base64.b64decode(coded_string)
    fileobj = _io._FilelikePreference()
    fileobj.write(decoded_data)
    fileobj.seek(0)
    return fileobj
