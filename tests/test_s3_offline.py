import hashlib
from io import BytesIO
from typing import BinaryIO
from unittest.mock import Mock

import pytest

from imagehelper.image_wrapper import BasicImage
from imagehelper.saver import s3

from .test_core import CustomSaverLogger
from .test_core import newResizerConfig
from .test_core import newSaverConfig


def test_s3_upload_and_delete(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise public S3 operations without contacting AWS."""
    saver_config = newSaverConfig()
    saver_logger = CustomSaverLogger()
    uploader = s3.SaverSimpleAccess(
        saverConfig=saver_config,
        saverLogger=saver_logger,
        resizerConfig=newResizerConfig(),
    )
    payload = b"image payload"
    bucket = saver_config.bucket_public_name
    filename = "image.jpg"

    def upload_fileobj(
        stream: BinaryIO,
        bucket_name: str,
        key: str,
        *,
        ExtraArgs: dict[str, str],
    ) -> None:
        """Check the transfer arguments and simulate the SDK closing the stream."""
        assert bucket_name == bucket
        assert key == filename
        assert ExtraArgs == {"ACL": "public-read", "ContentType": "image/jpeg"}
        assert stream.read() == payload
        stream.close()

    client = Mock(spec=["upload_fileobj", "delete_objects"])
    client.upload_fileobj.side_effect = upload_fileobj
    sdk = Mock(spec=["client"])
    sdk.client.return_value = client
    monkeypatch.setattr(s3, "boto3", sdk)

    with BytesIO(payload) as original:
        image = BasicImage(original, format="JPEG")
        planned = uploader.file_save("@public", filename, image, dry_run=True)
        sdk.client.assert_not_called()
        assert list(planned.values()) == [(filename, bucket)]
        assert uploader.files_delete(planned, dry_run=True) == {}
        sdk.client.assert_not_called()

        uploaded = uploader.file_save("@public", filename, image)
        assert list(uploaded.values()) == [(filename, bucket)]
        assert original.read() == payload
        assert saver_logger._saves == [
            (bucket, filename, len(payload), hashlib.md5(payload).hexdigest())
        ]

        assert uploader.files_delete(uploaded) == {}
        assert saver_logger._deletes == [(bucket, filename)]

    sdk.client.assert_called_once()
    client.upload_fileobj.assert_called_once()
    client.delete_objects.assert_called_once_with(
        Bucket=bucket, Delete={"Objects": [{"Key": filename}]}
    )
