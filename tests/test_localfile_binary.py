"""Verify local saving and binary file mode round trips."""

from io import BytesIO
from pathlib import Path

from imagehelper import _io
from imagehelper.image_wrapper import BasicImage
from imagehelper.saver.localfile import SaverConfig, SaverLogger, SaverSimpleAccess


def test_localfile_preserves_binary_bytes(tmp_path: Path) -> None:
    """Write and read bytes unchanged through the public local saver."""
    payload = b"\x00\xff\r\n\x80"
    saver = SaverSimpleAccess(
        saverConfig=SaverConfig(filedir=str(tmp_path)),
        saverLogger=SaverLogger(),
    )
    with BytesIO(payload) as stream:
        saved = saver.file_save("public", "image.png", BasicImage(stream, format="PNG"))
    target = tmp_path / "public" / "image.png"
    with target.open(_io.FileReadArgs) as stream:
        assert stream.read() == payload
    assert saver.files_delete(saved) == {}
    assert not target.exists()


def test_local_saver_rejects_external_destination(tmp_path: Path) -> None:
    """Reject saves and deletes whose resolved target is outside storage."""
    import pytest

    root = tmp_path / "storage"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "public").symlink_to(outside, target_is_directory=True)
    saver = SaverSimpleAccess(saverConfig=SaverConfig(filedir=str(root)))
    with BytesIO(b"image") as stream:
        with pytest.raises(ValueError, match="storage root"):
            saver.file_save("public", "image.png", BasicImage(stream, format="PNG"))
    with pytest.raises(ValueError, match="storage root"):
        saver.files_delete({"image": ("image.png", "public")}, dry_run=True)
