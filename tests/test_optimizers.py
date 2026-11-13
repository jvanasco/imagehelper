"""Exercise optimizer fallback and installed command-line tools."""

from copy import deepcopy
from io import BytesIO
import os
from pathlib import Path
import subprocess
from time import perf_counter
from statistics import median

from PIL import Image, ImageSequence
import pytest

from imagehelper import image_wrapper as wrapper


DATA = Path(__file__).parent / "test-data"
CASES = [
    ("JPEG", "jpegtran"), ("JPEG", "jpegoptim"),
    ("PNG", "pngcrush"), ("PNG", "optipng"), ("PNG", "advpng"),
    ("GIF", "gifsicle"),
]


def fixture_bytes(fmt: str) -> bytes:
    """Return representative input in the requested format."""
    if fmt == "PNG":
        with Image.open(DATA / "henry.jpg") as photo, BytesIO() as output:
            photo.thumbnail((320, 320))
            photo.save(output, "PNG", compress_level=1)
            return output.getvalue()
    return (DATA / ("henry.jpg" if fmt == "JPEG" else "spiral_animation.gif")).read_bytes()


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Isolate optimizer configuration for each test."""
    config = deepcopy(wrapper.OPTIMIZE_SUPPORT)
    monkeypatch.setattr(wrapper, "OPTIMIZE_SUPPORT", config)
    monkeypatch.setattr(wrapper, "_OPTIMIZE_SUPPORT_DETECTED", False)
    return config


def require_tool(settings: dict, name: str) -> None:
    """Skip absent optional tools locally and fail when CI requires them."""
    if not settings[name]["available"]:
        if os.environ.get("IMAGEHELPER_REQUIRE_OPTIMIZERS"):
            pytest.fail(f"Required optimizer missing: {name}")
        pytest.skip(f"Optimizer missing: {name}")


@pytest.mark.parametrize("failure", ["missing", "nonzero", "invalid"])
def test_preserves_source_on_failure(
    settings: dict, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    """Keep the original bytes when a tool is missing or its output is unusable."""
    settings["jpegoptim"]["use"] = False
    monkeypatch.setattr(
        wrapper.shutil, "which", lambda name: None if failure == "missing" else name
    )

    def run(command: list[str], **kwargs: object) -> None:
        if failure == "nonzero":
            raise subprocess.CalledProcessError(2, command)
        Path(command[command.index("-outfile") + 1]).write_bytes(b"invalid")

    monkeypatch.setattr(wrapper.subprocess, "run", run)
    payload = fixture_bytes("JPEG")
    wrapped = wrapper.BasicImage(BytesIO(payload), format="JPEG")
    wrapped.optimize()
    assert wrapped.file.read() == payload
    assert not wrapped.is_optimized
    assert wrapped.optimization_savings == 0
    assert wrapped.optimizations == ([] if failure == "missing" else [("jpegtran", False)])


@pytest.mark.parametrize(("fmt", "name"), CASES)
def test_installed_optimizer(settings: dict, fmt: str, name: str) -> None:
    """Run each optimizer independently and verify its decoded result."""
    wrapper.autodetect_support()
    require_tool(settings, name)
    for tool, config in settings.items():
        config["use"] = tool == name

    payload = fixture_bytes(fmt)
    wrapped = wrapper.BasicImage(BytesIO(payload), format=fmt)
    wrapped.optimize()
    assert wrapped.optimizations == [(name, True)]
    assert wrapped.file.tell() == 0
    assert wrapped.optimization_savings == len(payload) - wrapped.file_size
    with Image.open(BytesIO(payload)) as original, Image.open(wrapped.file) as result:
        assert result.format == fmt
        assert result.size == original.size
        if fmt == "PNG":
            assert result.convert("RGBA").tobytes() == original.convert("RGBA").tobytes()
        if fmt == "GIF":
            assert result.info.get("loop") == original.info.get("loop")
            assert [
                (frame.info.get("duration"), frame.convert("RGBA").tobytes())
                for frame in ImageSequence.Iterator(result)
            ] == [
                (frame.info.get("duration"), frame.convert("RGBA").tobytes())
                for frame in ImageSequence.Iterator(original)
            ]


@pytest.mark.parametrize("interlace", [True, False])
def test_gifsicle_interlace(settings: dict, interlace: bool) -> None:
    """Inspect the actual GIF interlace flag for each explicit setting."""
    wrapper.autodetect_support()
    require_tool(settings, "gifsicle")
    settings["gifsicle"]["options"]["interlace"] = interlace
    with BytesIO() as payload:
        Image.new("P", (32, 32)).save(payload, "GIF")
        wrapped = wrapper.BasicImage(payload, format="GIF")
        wrapped.optimize()
        assert wrapped.optimizations == [("gifsicle", True)]
        output = subprocess.check_output(
            [settings["gifsicle"]["binary"] or "gifsicle", "--info"],
            input=wrapped.file.read(),
            stderr=subprocess.STDOUT,
        )
    assert (b"interlaced" in output) is interlace


@pytest.mark.skipif(
    not os.environ.get("IMAGEHELPER_BENCHMARK"), reason="opt-in optimizer benchmark"
)
@pytest.mark.parametrize(("fmt", "name"), CASES + [
    ("JPEG", "default"), ("PNG", "default"), ("GIF", "default"),
])
def test_optimizer_benchmark(settings: dict, fmt: str, name: str) -> None:
    """Measure the end-to-end optimizer runtime and encoded byte count."""
    wrapper.autodetect_support()
    if name != "default":
        require_tool(settings, name)
        for tool, config in settings.items():
            config["use"] = tool == name

    payload = fixture_bytes(fmt)
    timings = []
    for _ in range(5):
        wrapped = wrapper.BasicImage(BytesIO(payload), format=fmt)
        start = perf_counter()
        wrapped.optimize()
        timings.append(perf_counter() - start)
        result_size = wrapped.file_size
        stages = wrapped.optimizations or []
        assert stages and all(success for _, success in stages)
    change = 100 * (result_size - len(payload)) / len(payload)
    print(
        f"{fmt:4} {name:10} {median(timings) * 1000:8.2f} ms "
        f"{len(payload):9} -> {result_size:9} bytes ({change:+.2f}%) "
        f"[{', '.join(tool for tool, _ in stages)}]"
    )
