from io import BytesIO
from io import StringIO
from pathlib import Path

import pytest
from PIL import Image

from imagehelper import errors
from imagehelper.image_wrapper import ImageWrapper
from imagehelper.utils import ImageErrorCodes


def test_invalid_image_closes_copy_and_rewinds_input() -> None:
    """Release the temporary copy and preserve ownership of the input stream."""
    copies: list[BytesIO] = []

    class TrackedCopy(BytesIO):
        """Record the temporary stream created by the loader."""

        def __init__(self) -> None:
            super().__init__()
            copies.append(self)

    with BytesIO(b"invalid image") as source:
        source.seek(3)
        with pytest.raises(errors.ImageError_Parsing) as exc:
            ImageWrapper(source, FilelikePreference=TrackedCopy)
        assert exc.value.args == (ImageErrorCodes.INVALID_FILETYPE,)
        assert isinstance(exc.value.__cause__, OSError)
        assert source.tell() == 0
    assert len(copies) == 1
    assert copies[0].closed


def test_text_stream_is_rejected_and_rewound() -> None:
    """Report a parsing error when the input stream returns text."""
    with StringIO("invalid image") as source:
        source.seek(3)
        with pytest.raises(errors.ImageError_Parsing) as exc:
            ImageWrapper(source)
        assert exc.value.args == (ImageErrorCodes.INVALID_FILETYPE,)
        assert source.tell() == 0


def test_pillow_pixel_limit_is_reported_as_parsing_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Honor Pillow's pixel limit and preserve the cause of the parsing error."""
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1)
    payload = (Path(__file__).parent / "test-data" / "henry.jpg").read_bytes()
    with BytesIO(payload) as source:
        with pytest.raises(errors.ImageError_Parsing) as exc:
            ImageWrapper(source)
        assert exc.value.args == (ImageErrorCodes.INVALID_FILETYPE,)
        assert isinstance(exc.value.__cause__, Image.DecompressionBombError)
        assert source.tell() == 0
