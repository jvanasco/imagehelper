"""Exercise animated GIF policy, resource limits, and playback."""

from io import BytesIO
import shutil

from PIL import Image, ImageDraw, ImageSequence
import pytest

from imagehelper import errors
from imagehelper._types import ResizerInstructions
from imagehelper.image_wrapper import ANTIALIAS, ImageWrapper
from imagehelper.resizer import Resizer, ResizerConfig
from imagehelper.utils import ImageErrorCodes


@pytest.fixture
def animated_gif() -> bytes:
    """Build transparent frames with mixed disposal and uneven delays."""
    frames = []
    for x, color in [(0, "red"), (8, "blue"), (16, "green")]:
        frame = Image.new("RGBA", (24, 16))
        ImageDraw.Draw(frame).rectangle((x, 0, x + 7, 7), fill=color)
        frames.append(frame)
    with BytesIO() as stream:
        frames[0].save(
            stream, "GIF", save_all=True, append_images=frames[1:],
            disposal=[1, 2, 3], duration=[40, 130, 70], loop=2, optimize=False,
        )
        return stream.getvalue()


def recipe(allow_animated: bool = True, fmt: str = "GIF") -> ResizerInstructions:
    """Return a recipe that halves the test canvas."""
    return {
        "width": 12,
        "height": 8,
        "constraint-method": "fit-within",
        "format": fmt,
        "allow_animated": allow_animated,
    }


def test_default_rejects_disguised_animation(animated_gif: bytes) -> None:
    """Apply the upload policy to GIF content regardless of its name."""
    with pytest.raises(errors.ImageError_Parsing) as exc:
        ImageWrapper(BytesIO(animated_gif), imagefile_name="photo.jpg")
    assert exc.value.args == (ImageErrorCodes.ANIMATION_NOT_ALLOWED,)


@pytest.mark.parametrize(("frames", "pixels"), [(2, 2000), (3, 1151)])
def test_input_budget(animated_gif: bytes, frames: int, pixels: int) -> None:
    """Reject animations that exceed either input resource limit."""
    with pytest.raises(errors.ImageError_Parsing) as exc:
        ImageWrapper(
            BytesIO(animated_gif), allow_animated_gif=True,
            max_animation_frames=frames, max_animation_pixels=pixels,
        )
    assert exc.value.args == (ImageErrorCodes.ANIMATION_LIMIT_EXCEEDED,)


@pytest.mark.parametrize(("allowed", "fmt"), [(False, "GIF"), (True, "PNG")])
def test_recipe_requires_explicit_gif_output(
    animated_gif: bytes, allowed: bool, fmt: str
) -> None:
    """Require the second opt-in and an animated-capable output format."""
    wrapper = ImageWrapper(
        BytesIO(animated_gif), allow_animated_gif=True,
        max_animation_frames=3, max_animation_pixels=2000,
    )
    with pytest.raises(errors.ImageError_InstructionsError):
        wrapper.resize(recipe(allowed, fmt))


def test_wrapped_upload_cannot_bypass_policy(animated_gif: bytes) -> None:
    """Recheck the policy when a caller supplies an existing wrapper."""
    wrapper = ImageWrapper(
        BytesIO(animated_gif), allow_animated_gif=True,
        max_animation_frames=3, max_animation_pixels=2000,
    )
    with pytest.raises(errors.ImageError_Parsing) as exc:
        Resizer(ResizerConfig()).register_image_file(imageWrapper=wrapper)
    assert exc.value.args == (ImageErrorCodes.ANIMATION_NOT_ALLOWED,)


def test_output_budget_is_shared_across_recipes(animated_gif: bytes) -> None:
    """Charge input and both requested animated outputs to the same budget."""
    config = ResizerConfig(
        resizesSchema={"first": recipe(), "second": recipe()},
        allow_animated_gif=True, max_animation_frames=3, max_animation_pixels=1727,
    )
    with pytest.raises(errors.ImageError_ResizeError, match="pixel budget"):
        Resizer(config).resize(imagefile=BytesIO(animated_gif))


def playback(image: Image.Image) -> list[tuple[int, bytes]]:
    """Return decoded timing and visible pixels, ignoring hidden RGB values."""
    result = []
    for frame in ImageSequence.Iterator(image):
        rgba = frame.convert("RGBA")
        visible = Image.alpha_composite(Image.new("RGBA", rgba.size), rgba)
        result.append((frame.info.get("duration", 0), visible.tobytes()))
    return result


@pytest.mark.parametrize("optimize", [False, True])
def test_resized_playback(animated_gif: bytes, optimize: bool) -> None:
    """Keep dimensions, visible disposal, transparency, timing, and looping."""
    if optimize and not shutil.which("gifsicle"):
        pytest.skip("gifsicle is unavailable")
    config = ResizerConfig(
        resizesSchema={"small": recipe()}, optimize_resized=optimize,
        allow_animated_gif=True, max_animation_frames=3, max_animation_pixels=1440,
    )
    result = Resizer(config).resize(imagefile=BytesIO(animated_gif)).resized["small"]
    assert result.animated_image_totalframes == 3
    if optimize:
        assert result.optimizations == [("gifsicle", True)]
    with Image.open(result.file) as output, Image.open(BytesIO(animated_gif)) as source:
        assert output.size == (12, 8)
        assert output.info["loop"] == source.info["loop"] == 2
        decoded = playback(output)
        assert [duration for duration, _ in decoded] == [40, 130, 70]
        for index, (_, pixels) in enumerate(decoded):
            source.seek(index)
            expected = source.convert("RGBA").resize(output.size, ANTIALIAS)
            expected.putalpha(expected.getchannel("A").point(lambda a: 255 if a >= 128 else 0))
            expected = Image.alpha_composite(Image.new("RGBA", output.size), expected)
            assert pixels == expected.tobytes()
