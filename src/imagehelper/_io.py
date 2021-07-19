"""
consolidated way to figure out what files/filetypes are possible

this library once tried to support StringIO.StringIO; bugs with the botocore
and s3transfer library require a workaround that necessitates io
"""
# stdlib
import io
import tempfile

from ._compat import PY2

if PY2:
    # Python 2: "file" is built-in
    _CoreFileTypes = (
        file,
        io.IOBase,
    )
    _DefaultMemoryType = io.BytesIO
    # _FallbackFileType = tempfile.SpooledTemporaryFile
    _FilelikePreference = io.BytesIO
    FileReadArgs = "r"
    FileWriteArgs = "w"
else:
    # Python 3: "file" fully replaced with IOBase
    _CoreFileTypes = (io.IOBase,)
    _DefaultMemoryType = io.BytesIO
    # _FallbackFileType = tempfile.SpooledTemporaryFile
    _FilelikePreference = io.BytesIO
    FileReadArgs = "rb"
    FileWriteArgs = "wb"
