"""
this is our consolidated way to figure out what files/filetypes are possible
"""
# stdlib
import tempfile

# pypi
import six

# ---- StringIO fun ---------
# Python3 - io.BytesIO
# Python3 - io.StringIO
# Python2 - StringIO.StringIO
# Python2 - cStringIO.InputType
# Python2 - cStringIO.OutputType
# Python2 - cStringIO.StringIO
from six.moves import StringIO  # Py3= io.StringIO ; Py2= StringIO.StringIO
cStringIO = None
if six.PY2:
    try:
        # only happens in Python2
        import cStringIO
    except ImportError:
        pass
# ---- END StringIO fun ---------


if six.PY2:
    _CoreFileType = file
    _DefaultMemoryType = cStringIO.StringIO if cStringIO else StringIO
    _FallbackFileType = tempfile.SpooledTemporaryFile
    FileReadArgs = 'r'
    FileWriteArgs = 'w'
else:
    import io
    _CoreFileType = io.IOBase
    _DefaultMemoryType = io.BytesIO
    _FallbackFileType = _DefaultMemoryType
    FileReadArgs = 'rb'
    FileWriteArgs = 'wb'
