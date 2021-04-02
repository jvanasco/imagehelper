"""
consolidated way to figure out what files/filetypes are possible

under Python2:
    cStringIO is faster than StringIO
under Python3
    StringIO is cStringIO
"""
# stdlib
import tempfile

from ._compat import PY2
from ._compat import StringIO

# ---- StringIO fun ---------
# Python3 - io.BytesIO
# Python3 - io.StringIO
# Python2 - StringIO.StringIO
# Python2 - cStringIO.InputType
# Python2 - cStringIO.OutputType
# Python2 - cStringIO.StringIO
cStringIO = None
if PY2:
    try:
        # only happens in Python2
        import cStringIO
    except ImportError:
        pass
# ---- END StringIO fun ---------


if PY2:
    _CoreFileType = file
    _DefaultMemoryType = cStringIO.StringIO if cStringIO else StringIO
    _FallbackFileType = tempfile.SpooledTemporaryFile
    FileReadArgs = "r"
    FileWriteArgs = "w"
else:
    import io

    _CoreFileType = io.IOBase
    _DefaultMemoryType = io.BytesIO
    _FallbackFileType = _DefaultMemoryType
    FileReadArgs = "rb"
    FileWriteArgs = "wb"
