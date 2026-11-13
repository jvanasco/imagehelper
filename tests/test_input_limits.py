"""Verify the input limits across the image-loading entry points."""

from base64 import b64encode
from io import BytesIO

from PIL import Image
import pytest

from imagehelper import errors
from imagehelper.image_wrapper import ImageWrapper
from imagehelper.resizer import Resizer, ResizerConfig, ResizerFactory
from imagehelper.utils import ImageErrorCodes


@pytest.fixture
def png_bytes() -> bytes:
    """Generate a small rectangular image for testing independent axis limits."""
    with BytesIO() as stream:
        Image.new("RGB", (13, 7), "red").save(stream, "PNG")
        return stream.getvalue()


def test_stream_limits_are_inclusive(png_bytes: bytes) -> None:
    """Load an image exactly at the byte, width, and height limits."""
    with BytesIO(png_bytes) as source:
        wrapped = ImageWrapper(
            source, max_filesize=len(png_bytes), max_dimensions=(13, 7)
        )
        assert wrapped.pilObject.size == (13, 7)
        assert source.tell() == 0


def test_reject_oversize_stream_before_reading(png_bytes: bytes) -> None:
    """Reject an oversized seekable input without reading or closing it."""
    class Unreadable(BytesIO):
        def read(self, size: int = -1, /) -> bytes:
            pytest.fail("Oversized input should not be read")

    with Unreadable(png_bytes) as source:
        with pytest.raises(errors.ImageError_Parsing) as exc:
            ImageWrapper(source, max_filesize=len(png_bytes) - 1)
        assert exc.value.args == (ImageErrorCodes.FILESIZE_LIMIT_EXCEEDED,)
        assert source.tell() == 0


@pytest.mark.parametrize("dimensions", [(12, 7), (13, 6)])
def test_factory_rejects_either_axis_before_decode(
    png_bytes: bytes,
    dimensions: tuple[int, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Enforce the configured dimensions before Pillow decodes pixels."""
    def unexpected_load(*args: object) -> None:
        pytest.fail("Oversized image should not be decoded")

    from PIL.PngImagePlugin import PngImageFile

    monkeypatch.setattr(PngImageFile, "load", unexpected_load)
    factory = ResizerFactory(ResizerConfig(max_dimensions=dimensions))
    with BytesIO(png_bytes) as source:
        with pytest.raises(errors.ImageError_Parsing) as exc:
            factory.resizer(imagefile=source)
        assert exc.value.args == (ImageErrorCodes.DIMENSIONS_LIMIT_EXCEEDED,)


@pytest.mark.parametrize("entry", ["base64", "wrapped"])
def test_registration_checks_alternate_inputs(png_bytes: bytes, entry: str) -> None:
    """Apply the byte limit to decoded Base64 and already wrapped images."""
    resizer = Resizer(ResizerConfig(max_filesize=len(png_bytes) - 1))
    with BytesIO(png_bytes) as source, pytest.raises(errors.ImageError_Parsing) as exc:
        if entry == "base64":
            resizer.register_image_file(file_b64=b64encode(png_bytes))
        else:
            resizer.register_image_file(imageWrapper=ImageWrapper(source))
    assert exc.value.args == (ImageErrorCodes.FILESIZE_LIMIT_EXCEEDED,)


def test_passthrough_keeps_original_dimensions(png_bytes: bytes) -> None:
    """Exercise the eighth resize constraint with omitted target dimensions."""
    config = ResizerConfig(
        resizesSchema={
            "original_size": {
                "width": None,
                "height": None,
                "constraint-method": "passthrough:no-resize",
                "format": "PNG",
            }
        }
    )
    with BytesIO(png_bytes) as source:
        result = Resizer(config).resize(imagefile=source)
    resized = result.resized["original_size"]
    with Image.open(resized.file) as output:
        assert output.size == (13, 7)
        assert output.getpixel((0, 0)) == (255, 0, 0)


def test_base64_limit_checks_before_decode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reject excess encoded input before allocating a decoded buffer."""
    from imagehelper import utils

    def unexpected_decode(encoded: bytes) -> BytesIO:
        pytest.fail("Oversized Base64 should not be decoded")

    monkeypatch.setattr(utils, "b64_decode_to_file", unexpected_decode)
    resizer = Resizer(ResizerConfig(max_filesize=3))
    with pytest.raises(errors.ImageError_Parsing) as exc:
        resizer.register_image_file(file_b64=b"YWJj\nZA==")
    assert exc.value.args == (ImageErrorCodes.FILESIZE_LIMIT_EXCEEDED,)
