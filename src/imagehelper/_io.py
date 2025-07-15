"""
consolidated way to figure out what files/filetypes are possible

this library once tried to support StringIO.StringIO; bugs with the botocore
and s3transfer library require a workaround that necessitates io
"""

# stdlib
import cgi
import io
from typing import Type
from typing import Union

# ==============================================================================

_CoreFileTypes = (io.IOBase,)
_DefaultMemoryType = io.BytesIO
# _FallbackFileType = tempfile.SpooledTemporaryFile
_FilelikePreference = io.BytesIO
FileReadArgs = "rb"
FileWriteArgs = "wb"

TYPES_FilelikeSupported = Type[io.BytesIO]
TYPES_imagefile_a = Union[
    cgi.FieldStorage,
    io.IOBase,
]
