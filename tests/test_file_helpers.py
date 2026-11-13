import base64
import hashlib
from io import BytesIO

import pytest

from imagehelper import utils


@pytest.mark.parametrize("payload", [b"", bytes(range(256)) * 32])
def test_file_helpers_rewind(payload: bytes) -> None:
    """Read the entire stream and leave it rewound after each operation."""
    with BytesIO(payload) as stream:
        stream.seek(len(payload))
        assert utils.file_size(stream) == len(payload)
        assert stream.tell() == 0

        stream.seek(len(payload))
        assert utils.file_md5(stream) == hashlib.md5(payload).hexdigest()
        assert stream.tell() == 0

        stream.seek(len(payload))
        encoded = utils.file_b64(stream)
        assert encoded == base64.encodebytes(payload)
        assert stream.tell() == 0

    with utils.b64_decode_to_file(encoded) as decoded:
        assert decoded.tell() == 0
        assert decoded.read() == payload
