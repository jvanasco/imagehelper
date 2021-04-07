from __future__ import print_function

# stdlib
import unittest
import pdb  # noqa
import os

# pypi
import requests

# local
import imagehelper
from imagehelper import _io

# by default, do not test S3 connectivity, as that relies on secrets
TEST_S3 = int(os.environ.get("TEST_S3", 0))

# local - popular
# github secrets
AWS_KEY_PUBLIC = os.environ.get("AWS_KEY_PUBLIC", "12345")
AWS_KEY_SECRET = os.environ.get("AWS_KEY_SECRET", "54321")
AWS_BUCKET_PUBLIC = os.environ.get("AWS_BUCKET_PUBLIC", "bucket-public")
AWS_BUCKET_ARCHIVE = os.environ.get("AWS_BUCKET_ARCHIVE", "bucket-archive")
AWS_BUCKET_ALT = os.environ.get("AWS_BUCKET_ALT", "bucket-alt")


LOCALFILE_DIRECTORY = "tests/localfile-output"

# ------------------------------------------------------------------------------


resizesSchema = {
    "thumb1": {
        "width": 120,
        "height": 120,
        "save_quality": 50,
        "suffix": "t1",
        "format": "JPEG",
        "constraint-method": "fit-within",
        "filename_template": "%(guid)s.%(format)s",
        "s3_headers": {"x-amz-acl": "public-read"},
    },
    "t2": {
        "width": 120,
        "height": 120,
        "save_quality": 50,
        "suffix": "t2",
        "format": "PDF",
        "constraint-method": "fit-within:ensure-width",
    },
    "thumb3": {
        "width": 120,
        "height": 120,
        "format": "GIF",
        "constraint-method": "fit-within:ensure-height",
    },
    "t4": {
        "width": 120,
        "height": 120,
        "save_optimize": True,
        "filename_template": "%(guid)s---%(suffix)s.%(format)s",
        "suffix": "t4",
        "format": "PNG",
        "constraint-method": "fit-within:crop-to",
    },
}
selected_resizes = ["thumb1", "t2", "thumb3", "t4"]

_img = None


def get_imagefile():
    global _img
    if _img is None:
        # py3-  r= _io.TextIOWrapper
        # py3-  rb= _io.BufferedReader
        img = open("tests/test-data/henry.jpg", _io.FileReadArgs)
        img.seek(0)
        data = img.read()
        img.close()
        imgMemory = _io._DefaultMemoryType()
        imgMemory.write(data)
        _img = imgMemory
    _img.seek(0)
    return _img


def newSaverConfig():
    """
    save the files into AmazonS3
    """
    saverConfig = imagehelper.saver.s3.SaverConfig(
        key_public=AWS_KEY_PUBLIC,
        key_private=AWS_KEY_SECRET,
        bucket_public_name=AWS_BUCKET_PUBLIC,
        bucket_archive_name=AWS_BUCKET_ARCHIVE,
        bucket_public_headers={"x-amz-acl": "public-read"},
        bucket_archive_headers={},
        archive_original=True,
    )

    return saverConfig


def newSaverConfig_Localfile():
    """
    save the files into a folder with the same names as our AWS buckets
    """
    saverConfig = imagehelper.saver.localfile.SaverConfig(
        subdir_public_name=AWS_BUCKET_PUBLIC,
        subdir_archive_name=AWS_BUCKET_ARCHIVE,
        archive_original=True,
        filedir=LOCALFILE_DIRECTORY,
    )

    return saverConfig


def newResizerConfig(optimize_original=True, optimize_resized=True):
    resizerConfig = imagehelper.resizer.ResizerConfig(
        resizesSchema=resizesSchema,
        selected_resizes=selected_resizes,
        optimize_original=optimize_original,
        optimize_resized=optimize_resized,
    )
    return resizerConfig


def newSaverLogger():
    saverLogger = imagehelper.saver.s3.SaverLogger()
    return saverLogger


class CustomSaverLogger(imagehelper.saver.s3.SaverLogger):
    def __init__(self):
        self._saves = []
        self._deletes = []

    def log_save(self, bucket_name=None, key=None, file_size=None, file_md5=None):
        # todo: change to logger and/or mock
        print("CustomSaverLogger.log_save")
        print("\t %s, %s, %s, %s" % (bucket_name, key, file_size, file_md5))
        self._saves.append((bucket_name, key, file_size, file_md5))

    def log_delete(self, bucket_name=None, key=None):
        # todo: change to logger and/or mock
        print("CustomSaverLogger.log_delete")
        print("\t %s, %s" % (bucket_name, key))
        self._deletes.append((bucket_name, key))


class _ImagehelperTestingMixin(object):
    def _check_resizedImages(self, resizedImages):
        # ensure the original has a file size
        self.assertNotEqual(resizedImages.original.file_size, 0)

        # ensure every resize has a file_size
        for _size in resizedImages.resized.keys():
            self.assertNotEqual(resizedImages.resized[_size].file_size, 0)


class TestResize(unittest.TestCase, _ImagehelperTestingMixin):
    def test_direct_resize(self):

        # new resizer config
        resizerConfig = newResizerConfig()

        # build a new resizer
        resizer = imagehelper.resizer.Resizer(resizerConfig=resizerConfig)

        # try to register the image
        resizer.register_image_file(imagefile=get_imagefile())

        try:
            # resize the image
            # this should fail, because we don't want to risk changing the image before registering
            results = resizer.resize(imagefile=get_imagefile())
            raise ValueError("this should have failed")
        except imagehelper.errors.ImageError_DuplicateAction:
            # expected!
            pass

        # build a new resizer
        resizer = imagehelper.resizer.Resizer(resizerConfig=resizerConfig)
        # resize the image
        resizedImages = resizer.resize(imagefile=get_imagefile())

        # audit the payload
        self._check_resizedImages(resizedImages)


class TestS3(unittest.TestCase, _ImagehelperTestingMixin):
    def test_s3_factory(self):

        # generate the configs
        resizerConfig = newResizerConfig()
        saverConfig = newSaverConfig()
        saverLogger = newSaverLogger()

        # generate the factory
        saverManagerFactory = imagehelper.saver.s3.SaverManagerFactory(
            saverConfig=saverConfig,
            saverLogger=saverLogger,
            resizerConfig=resizerConfig,
        )

        # grab a manager
        saverManager = saverManagerFactory.saver_manager()

        # make sure we generated a manager
        assert isinstance(saverManager, imagehelper.saver.s3.SaverManager)

        # inspect the manager to ensure it is set up correctly
        assert saverManager._saverConfig == saverConfig
        assert saverManager._saverLogger == saverLogger
        assert saverManager._resizerConfig == resizerConfig

    @unittest.skipUnless(TEST_S3, "S3 Testing Disabled")
    def test_s3__saver_manager(self):
        """
        test saving files with the `localfile.SaverManager`
        """

        # new resizer config
        resizerConfig = newResizerConfig()
        # build a factory
        resizerFactory = imagehelper.resizer.ResizerFactory(resizerConfig=resizerConfig)

        # grab a resizer
        resizer = resizerFactory.resizer()

        # resize !
        resizedImages = resizer.resize(imagefile=get_imagefile())

        # audit the payload
        self._check_resizedImages(resizedImages)

        # new s3 config
        saverConfig = newSaverConfig()
        # new s3 logger
        # saverLogger = imagehelper.saver.s3.SaverLogger()
        saverLogger = CustomSaverLogger()

        # upload the resized items
        uploader = imagehelper.saver.s3.SaverManager(
            saverConfig=saverConfig,
            resizerConfig=resizerConfig,
            saverLogger=saverLogger,
        )

        guid = "123"
        uploaded = uploader.files_save(resizedImages, guid)
        deleted = uploader.files_delete(uploaded)

    @unittest.skipUnless(TEST_S3, "S3 Testing Disabled")
    def test_s3__saver_simple_access(self):
        """
        test saving files with the `localfile.SaverSimpleAccess`
        """

        # new resizer config
        resizerConfig = newResizerConfig()
        # build a factory
        resizerFactory = imagehelper.resizer.ResizerFactory(resizerConfig=resizerConfig)

        # grab a resizer
        resizer = resizerFactory.resizer()

        # resize !
        resizedImages = resizer.resize(imagefile=get_imagefile())

        # audit the payload
        self._check_resizedImages(resizedImages)

        # new s3 config
        saverConfig = newSaverConfig()
        # new s3 logger
        # saverLogger = imagehelper.saver.s3.SaverLogger()
        saverLogger = CustomSaverLogger()

        # upload the resized items
        uploader = imagehelper.saver.s3.SaverSimpleAccess(
            saverConfig=saverConfig,
            resizerConfig=resizerConfig,
            saverLogger=saverLogger,
        )

        guid = "123"
        filename = "%s.jpg" % guid
        bucket_name = saverConfig.bucket_public_name
        uploaded = uploader.file_save(
            bucket_name,
            filename,
            resizedImages.resized["thumb1"],
            upload_type="public",
            dry_run=False,
        )
        assert uploaded
        assert len(saverLogger._saves) == 1

        s3_url = "https://%s.s3.amazonaws.com/%s" % (bucket_name, filename)
        resp = requests.get(s3_url)
        assert resp.status_code == 200
        assert resp.headers["Content-Type"] == "image/jpeg"

        # but still rely on the parent class' call `files_delete` (fileS)
        deleted = uploader.files_delete(uploaded)
        assert isinstance(deleted, dict)
        assert len(deleted.items()) == 0
        assert len(saverLogger._deletes) == 1

        # and check it's not available any longer
        resp2 = requests.get(s3_url)
        assert resp2.status_code == 403


class TestLocalfile(unittest.TestCase, _ImagehelperTestingMixin):
    def test_localfile__saver_manager(self):
        """
        test saving files with the `localfile.SaverManager`
        """

        # new resizer config
        resizerConfig = newResizerConfig()
        # build a factory
        resizerFactory = imagehelper.resizer.ResizerFactory(resizerConfig=resizerConfig)

        # grab a resizer
        resizer = resizerFactory.resizer()

        # resize !
        resizedImages = resizer.resize(imagefile=get_imagefile())

        # audit the payload
        self._check_resizedImages(resizedImages)

        # new s3 config
        saverConfig = newSaverConfig_Localfile()
        # new s3 logger
        saverLogger = imagehelper.saver.localfile.SaverLogger()

        # upload the resized items
        saver = imagehelper.saver.localfile.SaverManager(
            saverConfig=saverConfig,
            resizerConfig=resizerConfig,
            saverLogger=saverLogger,
        )

        guid = "123"
        uploaded = saver.files_save(resizedImages, guid)
        deleted = saver.files_delete(uploaded)

    def test_localfile__saver_simple_access(self):
        """
        test saving files with the `localfile.SaverSimpleAccess`
        """

        # new resizer config
        resizerConfig = newResizerConfig()
        # build a factory
        resizerFactory = imagehelper.resizer.ResizerFactory(resizerConfig=resizerConfig)

        # grab a resizer
        resizer = resizerFactory.resizer()

        # resize !
        resizedImages = resizer.resize(imagefile=get_imagefile())

        # audit the payload
        self._check_resizedImages(resizedImages)

        # new saver config
        saverConfig = newSaverConfig_Localfile()
        # new logger
        saverLogger = imagehelper.saver.localfile.SaverLogger()

        # upload the resized items
        saver = imagehelper.saver.localfile.SaverSimpleAccess(
            saverConfig=saverConfig,
            resizerConfig=resizerConfig,
            saverLogger=saverLogger,
        )

        subdir_name = "test_localfile_simple"
        filename = "thumb1.jpg"

        # note we call `file_save` (file)
        uploaded = saver.file_save(
            subdir_name, filename, resizedImages.resized["thumb1"]
        )
        assert uploaded

        # test the directory is there
        _subdirs = os.listdir(LOCALFILE_DIRECTORY)
        assert "test_localfile_simple" in _subdirs

        # but still rely on the parent class' call `files_delete` (fileS)
        deleted = saver.files_delete(uploaded)

        # test the directory is now not-there, because it was cleaned up
        _subdirs = os.listdir(LOCALFILE_DIRECTORY)
        assert "test_localfile_simple" not in _subdirs


class TestResizingMethods(unittest.TestCase, _ImagehelperTestingMixin):
    def test_fit_within(self):
        method = "fit-within"
        schema = {
            "test": {
                "width": 120,
                "height": 120,
                "save_optimize": True,
                "format": "PNG",
                "constraint-method": method,
            }
        }

        # what do we expect ?
        expected_original_wh = (1200, 1600)
        expected_resized_wh = (90, 120)

        r = imagehelper.resizer.Resizer()
        resizedImages = r.resize(
            imagefile=get_imagefile(),
            resizesSchema=schema,
            selected_resizes=("test",),
            optimize_original=False,
            optimize_resized=True,
        )

        # audit the payload
        self._check_resizedImages(resizedImages)

        # what do we have ?
        actual_original_wh = (
            resizedImages.original.width,
            resizedImages.original.height,
        )
        actual_resized_wh = (
            resizedImages.resized["test"].width,
            resizedImages.resized["test"].height,
        )

        # assert the original matches
        assert expected_original_wh[0] == actual_original_wh[0]
        assert expected_original_wh[1] == actual_original_wh[1]

        # assert the resize matches
        assert expected_resized_wh[0] == actual_resized_wh[0]
        assert expected_resized_wh[1] == actual_resized_wh[1]

    def test_fit_within_crop_to(self):
        method = "fit-within:crop-to"
        schema = {
            "test": {
                "width": 120,
                "height": 120,
                "save_optimize": True,
                "format": "PNG",
                "constraint-method": method,
            }
        }

        # what do we expect ?
        expected_original_wh = (1200, 1600)
        expected_resized_wh = (120, 120)

        r = imagehelper.resizer.Resizer()
        resizedImages = r.resize(
            imagefile=get_imagefile(),
            resizesSchema=schema,
            selected_resizes=("test",),
            optimize_original=False,
            optimize_resized=True,
        )

        # audit the payload
        self._check_resizedImages(resizedImages)

        # what do we have ?
        actual_original_wh = (
            resizedImages.original.width,
            resizedImages.original.height,
        )
        actual_resized_wh = (
            resizedImages.resized["test"].width,
            resizedImages.resized["test"].height,
        )

        # assert the original matches
        assert expected_original_wh[0] == actual_original_wh[0]
        assert expected_original_wh[1] == actual_original_wh[1]

        # assert the resize matches
        assert expected_resized_wh[0] == actual_resized_wh[0]
        assert expected_resized_wh[1] == actual_resized_wh[1]

    def test_fit_within_ensure_width(self):
        method = "fit-within:ensure-width"
        schema = {
            "test": {
                "width": 120,
                "height": 120,
                "save_optimize": True,
                "format": "PNG",
                "constraint-method": method,
            }
        }

        # what do we expect ?
        expected_original_wh = (1200, 1600)
        expected_resized_wh = (120, 160)

        r = imagehelper.resizer.Resizer()
        resizedImages = r.resize(
            imagefile=get_imagefile(),
            resizesSchema=schema,
            selected_resizes=("test",),
            optimize_original=False,
            optimize_resized=True,
        )

        # audit the payload
        self._check_resizedImages(resizedImages)

        # what do we have ?
        actual_original_wh = (
            resizedImages.original.width,
            resizedImages.original.height,
        )
        actual_resized_wh = (
            resizedImages.resized["test"].width,
            resizedImages.resized["test"].height,
        )

        # assert the original matches
        assert expected_original_wh[0] == actual_original_wh[0]
        assert expected_original_wh[1] == actual_original_wh[1]

        # assert the resize matches
        assert expected_resized_wh[0] == actual_resized_wh[0]
        assert expected_resized_wh[1] == actual_resized_wh[1]

    def test_fit_within_ensure_height(self):
        method = "fit-within:ensure-height"
        schema = {
            "test": {
                "width": 120,
                "height": 120,
                "save_optimize": True,
                "format": "PNG",
                "constraint-method": method,
            }
        }

        # what do we expect ?
        expected_original_wh = (1200, 1600)
        expected_resized_wh = (90, 120)

        r = imagehelper.resizer.Resizer()
        resizedImages = r.resize(
            imagefile=get_imagefile(),
            resizesSchema=schema,
            selected_resizes=("test",),
            optimize_original=False,
            optimize_resized=True,
        )
        # audit the payload
        self._check_resizedImages(resizedImages)

        # what do we have ?
        actual_original_wh = (
            resizedImages.original.width,
            resizedImages.original.height,
        )
        actual_resized_wh = (
            resizedImages.resized["test"].width,
            resizedImages.resized["test"].height,
        )

        # assert the original matches
        assert expected_original_wh[0] == actual_original_wh[0]
        assert expected_original_wh[1] == actual_original_wh[1]

        # assert the resize matches
        assert expected_resized_wh[0] == actual_resized_wh[0]
        assert expected_resized_wh[1] == actual_resized_wh[1]

    def test_fit_within_smallest_ensure_minimum(self):
        method = "smallest:ensure-minimum"
        schema = {
            "test": {
                "width": 120,
                "height": 120,
                "save_optimize": True,
                "format": "PNG",
                "constraint-method": method,
            }
        }

        # what do we expect ?
        expected_original_wh = (1200, 1600)
        expected_resized_wh = (120, 160)

        r = imagehelper.resizer.Resizer()
        resizedImages = r.resize(
            imagefile=get_imagefile(),
            resizesSchema=schema,
            selected_resizes=("test",),
            optimize_original=False,
            optimize_resized=True,
        )

        # audit the payload
        self._check_resizedImages(resizedImages)

        # what do we have ?
        actual_original_wh = (
            resizedImages.original.width,
            resizedImages.original.height,
        )
        actual_resized_wh = (
            resizedImages.resized["test"].width,
            resizedImages.resized["test"].height,
        )

        # assert the original matches
        assert expected_original_wh[0] == actual_original_wh[0]
        assert expected_original_wh[1] == actual_original_wh[1]

        # assert the resize matches
        assert expected_resized_wh[0] == actual_resized_wh[0]
        assert expected_resized_wh[1] == actual_resized_wh[1]

    def test_fit_within_exact_no_resize(self):
        method = "exact:no-resize"
        schema = {
            "test": {
                "width": 1200,
                "height": 1600,
                "save_optimize": True,
                "format": "PNG",
                "constraint-method": method,
            }
        }

        # what do we expect ?
        expected_original_wh = (1200, 1600)
        expected_resized_wh = (1200, 1600)

        r = imagehelper.resizer.Resizer()
        resizedImages = r.resize(
            imagefile=get_imagefile(),
            resizesSchema=schema,
            selected_resizes=("test",),
            optimize_original=False,
            optimize_resized=True,
        )

        # audit the payload
        self._check_resizedImages(resizedImages)

        # what do we have ?
        actual_original_wh = (
            resizedImages.original.width,
            resizedImages.original.height,
        )
        actual_resized_wh = (
            resizedImages.resized["test"].width,
            resizedImages.resized["test"].height,
        )

        # assert the original matches
        assert expected_original_wh[0] == actual_original_wh[0]
        assert expected_original_wh[1] == actual_original_wh[1]

        # assert the resize matches
        assert expected_resized_wh[0] == actual_resized_wh[0]
        assert expected_resized_wh[1] == actual_resized_wh[1]

    def test_fit_within_exact_proportion(self):
        method = "exact:proportion"
        schema = {
            "test": {
                "width": 240,
                "height": 320,
                "save_optimize": True,
                "format": "PNG",
                "constraint-method": method,
            }
        }

        # what do we expect ?
        expected_original_wh = (1200, 1600)
        expected_resized_wh = (240, 320)

        r = imagehelper.resizer.Resizer()
        resizedImages = r.resize(
            imagefile=get_imagefile(),
            resizesSchema=schema,
            selected_resizes=("test",),
            optimize_original=False,
            optimize_resized=True,
        )

        # audit the payload
        self._check_resizedImages(resizedImages)

        # what do we have ?
        actual_original_wh = (
            resizedImages.original.width,
            resizedImages.original.height,
        )
        actual_resized_wh = (
            resizedImages.resized["test"].width,
            resizedImages.resized["test"].height,
        )

        # assert the original matches
        assert expected_original_wh[0] == actual_original_wh[0]
        assert expected_original_wh[1] == actual_original_wh[1]

        # assert the resize matches
        assert expected_resized_wh[0] == actual_resized_wh[0]
        assert expected_resized_wh[1] == actual_resized_wh[1]
