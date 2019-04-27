from __future__ import print_function

# stdlib
import unittest
import pdb

# pypi
import six
from six.moves import configparser

# local
import imagehelper
from imagehelper import _io


# ------------------------------------------------------------------------------


resizesSchema = {
    'thumb1': {
        'width': 120,
        'height': 120,
        'save_quality': 50,
        'suffix': 't1',
        'format': 'JPEG',
        'constraint-method': 'fit-within',
        'filename_template': '%(guid)s.%(format)s',
        's3_headers': {'x-amz-acl': 'public-read'}
    },
    't2': {
        'width': 120,
        'height': 120,
        'save_quality': 50,
        'suffix': 't2',
        'format': 'PDF',
        'constraint-method': 'fit-within:ensure-width',
    },
    'thumb3': {
        'width': 120,
        'height': 120,
        'format': 'GIF',
        'constraint-method': 'fit-within:ensure-height',
    },
    't4': {
        'width': 120,
        'height': 120,
        'save_optimize': True,
        'filename_template': '%(guid)s---%(suffix)s.%(format)s',
        'suffix': 't4',
        'format': 'PNG',
        'constraint-method': 'fit-within:crop-to',
    },
}
selected_resizes = ['thumb1', 't2', 'thumb3', 't4']

_img = None


def get_imagefile():
    global _img
    if _img is None:
        # py3-  r= _io.TextIOWrapper
        # py3-  rb= _io.BufferedReader
        img = open('tests/henry.jpg', _io.FileReadArgs)
        img.seek(0)
        data = img.read()
        img.close()
        imgMemory = _io._DefaultMemoryType()
        imgMemory.write(data)
        _img = imgMemory
    _img.seek(0)
    return _img


def newSaverConfig():
    Config = configparser.ConfigParser()
    Config.read('aws.cfg')
    AWS_KEY_PUBLIC = Config.get('aws', 'AWS_KEY_PUBLIC')
    AWS_KEY_SECRET = Config.get('aws', 'AWS_KEY_SECRET')
    AWS_BUCKET_PUBLIC = Config.get('aws', 'AWS_BUCKET_PUBLIC')
    AWS_BUCKET_SECRET = Config.get('aws', 'AWS_BUCKET_SECRET')
    AWS_BUCKET_ALT = Config.get('aws', 'AWS_BUCKET_ALT')

    saverConfig = imagehelper.saver.s3.SaverConfig(
        key_public = AWS_KEY_PUBLIC,
        key_private = AWS_KEY_SECRET,
        bucket_public_name = AWS_BUCKET_PUBLIC,
        bucket_archive_name = AWS_BUCKET_SECRET,
        bucket_public_headers = {'x-amz-acl': 'public-read'},
        bucket_archive_headers = {},
        archive_original = True
    )

    return saverConfig


def newSaverConfig_Localfile():
    Config = configparser.ConfigParser()
    Config.read('aws.cfg')
    AWS_KEY_PUBLIC = Config.get('aws', 'AWS_KEY_PUBLIC')
    AWS_KEY_SECRET = Config.get('aws', 'AWS_KEY_SECRET')
    AWS_BUCKET_PUBLIC = Config.get('aws', 'AWS_BUCKET_PUBLIC')
    AWS_BUCKET_SECRET = Config.get('aws', 'AWS_BUCKET_SECRET')
    AWS_BUCKET_ALT = Config.get('aws', 'AWS_BUCKET_ALT')

    saverConfig = imagehelper.saver.localfile.SaverConfig(
    subdir_public_name = AWS_BUCKET_PUBLIC,
    subdir_archive_name = AWS_BUCKET_SECRET,
    archive_original = True
    )

    return saverConfig


def newResizerConfig(optimize_original=True, optimize_resized=True):
    resizerConfig = imagehelper.resizer.ResizerConfig(
        resizesSchema = resizesSchema,
        selected_resizes = selected_resizes,
        optimize_original = optimize_original,
        optimize_resized = optimize_resized,
    )
    return resizerConfig


def newSaverLogger():
    saverLogger = imagehelper.saver.s3.SaverLogger()
    return saverLogger


class CustomSaverLogger(imagehelper.saver.s3.SaverLogger):

    def log_save(self, bucket_name=None, key=None, file_size=None, file_md5=None):
        # todo: change to logger and/or mock
        print("CustomSaverLogger.log_save")
        print("\t %s, %s, %s, %s" % (bucket_name, key, file_size, file_md5))

    def log_delete(self, bucket_name=None, key=None):
        # todo: change to logger and/or mock
        print ("CustomSaverLogger.log_delete")
        print ("\t %s, %s" % (bucket_name, key))


class TestResize(unittest.TestCase):

    def test_direct_resize(self):

        # new resizer config
        resizerConfig = newResizerConfig()

        # build a new resizer
        resizer = imagehelper.resizer.Resizer(resizerConfig=resizerConfig)

        # try to register the image
        resizer.register_image_file(imagefile=get_imagefile(), )

        try:
            # resize the image
            # this should fail, because we don't want to risk changing the image before registering
            results = resizer.resize(imagefile=get_imagefile())
        except imagehelper.errors.ImageError_DuplicateAction:
            # expected!
            pass

        # build a new resizer
        resizer = imagehelper.resizer.Resizer(resizerConfig=resizerConfig)
        # resize the image
        resizedImages = resizer.resize(imagefile=get_imagefile())


class TestS3(unittest.TestCase):

    def test_s3_factory(self):

        # generate the configs
        resizerConfig = newResizerConfig()
        saverConfig = newSaverConfig()
        saverLogger = newSaverLogger()

        # generate the factory
        saverManagerFactory = imagehelper.saver.s3.SaverManagerFactory(saverConfig=saverConfig, saverLogger=saverLogger, resizerConfig=resizerConfig)

        # grab a manager
        saverManager = saverManagerFactory.saver_manager()

        # make sure we generated a manager
        assert isinstance(saverManager, imagehelper.saver.s3.SaverManager)

        # inspect the manager to ensure it is set up correctly
        assert saverManager._saverConfig == saverConfig
        assert saverManager._saverLogger == saverLogger
        assert saverManager._resizerConfig == resizerConfig

    def test_s3(self):

        # new resizer config
        resizerConfig = newResizerConfig()
        # build a factory
        resizerFactory = imagehelper.resizer.ResizerFactory(resizerConfig=resizerConfig)

        # grab a resizer
        resizer = resizerFactory.resizer()

        # resize !
        resizedImages = resizer.resize(imagefile=get_imagefile())

        # new s3 config
        saverConfig = newSaverConfig()
        # new s3 logger
        if False:
            saverLogger = imagehelper.saver.s3.SaverLogger()
        else:
            saverLogger = CustomSaverLogger()

        # upload the resized items
        uploader = imagehelper.saver.s3.SaverManager(saverConfig=saverConfig, resizerConfig=resizerConfig, saverLogger=saverLogger)

        guid = "123"
        uploaded = uploader.files_save(resizedImages, guid)
        deleted = uploader.files_delete(uploaded)


class TestLocalfile(unittest.TestCase):

    def test_localfile(self):

        # new resizer config
        resizerConfig = newResizerConfig()
        # build a factory
        resizerFactory = imagehelper.resizer.ResizerFactory(resizerConfig=resizerConfig)

        # grab a resizer
        resizer = resizerFactory.resizer()

        # resize !
        resizedImages = resizer.resize(imagefile=get_imagefile())

        # new s3 config
        saverConfig = newSaverConfig_Localfile()
        # new s3 logger
        saverLogger = imagehelper.saver.localfile.SaverLogger()

        # upload the resized items
        saver = imagehelper.saver.localfile.SaverManager(saverConfig=saverConfig, resizerConfig=resizerConfig, saverLogger=saverLogger)

        guid = "123"
        uploaded = saver.files_save(resizedImages, guid)
        deleted = saver.files_delete(uploaded)

class TestResizingMethods(unittest.TestCase):

    def test_fit_within(self):
        method = 'fit-within'
        schema = {
            'test': {
                'width': 120,
                'height': 120,
                'save_optimize': True,
                'format': 'PNG',
                'constraint-method': method,
            },
        }

        # what do we expect ?
        expected_original_wh = (1200, 1600)
        expected_resized_wh = (90, 120)

        r = imagehelper.resizer.Resizer()
        results = r.resize(imagefile=get_imagefile(), resizesSchema=schema, selected_resizes=('test', ), optimize_original=False, optimize_resized=True, )

        # what do we have ?
        actual_original_wh = (results.original.width, results.original.height)
        actual_resized_wh = (results.resized['test'].width, results.resized['test'].height)

        # assert the original matches
        assert expected_original_wh[0] == actual_original_wh[0]
        assert expected_original_wh[1] == actual_original_wh[1]

        # assert the resize matches
        assert expected_resized_wh[0] == actual_resized_wh[0]
        assert expected_resized_wh[1] == actual_resized_wh[1]

    def test_fit_within_crop_to(self):
        method = 'fit-within:crop-to'
        schema = {
            'test': {
                'width': 120,
                'height': 120,
                'save_optimize': True,
                'format': 'PNG',
                'constraint-method': method,
            },
        }

        # what do we expect ?
        expected_original_wh = (1200, 1600)
        expected_resized_wh = (120, 120)

        r = imagehelper.resizer.Resizer()
        results = r.resize(imagefile=get_imagefile(), resizesSchema=schema, selected_resizes=('test', ), optimize_original=False, optimize_resized=True)

        # what do we have ?
        actual_original_wh = (results.original.width, results.original.height)
        actual_resized_wh = (results.resized['test'].width, results.resized['test'].height)

        # assert the original matches
        assert expected_original_wh[0] == actual_original_wh[0]
        assert expected_original_wh[1] == actual_original_wh[1]

        # assert the resize matches
        assert expected_resized_wh[0] == actual_resized_wh[0]
        assert expected_resized_wh[1] == actual_resized_wh[1]

    def test_fit_within_ensure_width(self):
        method = 'fit-within:ensure-width'
        schema = {
            'test': {
                'width': 120,
                'height': 120,
                'save_optimize': True,
                'format': 'PNG',
                'constraint-method': method,
            },
        }

        # what do we expect ?
        expected_original_wh = (1200, 1600)
        expected_resized_wh = (120, 160)

        r = imagehelper.resizer.Resizer()
        results = r.resize(imagefile=get_imagefile(), resizesSchema=schema, selected_resizes=('test', ), optimize_original=False, optimize_resized=True)

        # what do we have ?
        actual_original_wh = (results.original.width, results.original.height)
        actual_resized_wh = (results.resized['test'].width, results.resized['test'].height)

        # assert the original matches
        assert expected_original_wh[0] == actual_original_wh[0]
        assert expected_original_wh[1] == actual_original_wh[1]

        # assert the resize matches
        assert expected_resized_wh[0] == actual_resized_wh[0]
        assert expected_resized_wh[1] == actual_resized_wh[1]

    def test_fit_within_ensure_height(self):
        method = 'fit-within:ensure-height'
        schema = {
            'test': {
                'width': 120,
                'height': 120,
                'save_optimize': True,
                'format': 'PNG',
                'constraint-method': method,
            },
        }

        # what do we expect ?
        expected_original_wh = (1200, 1600)
        expected_resized_wh = (90, 120)

        r = imagehelper.resizer.Resizer()
        results = r.resize(imagefile=get_imagefile(), resizesSchema=schema, selected_resizes=('test', ), optimize_original=False, optimize_resized=True)

        # what do we have ?
        actual_original_wh = (results.original.width, results.original.height)
        actual_resized_wh = (results.resized['test'].width, results.resized['test'].height)

        # assert the original matches
        assert expected_original_wh[0] == actual_original_wh[0]
        assert expected_original_wh[1] == actual_original_wh[1]

        # assert the resize matches
        assert expected_resized_wh[0] == actual_resized_wh[0]
        assert expected_resized_wh[1] == actual_resized_wh[1]

    def test_fit_within_smallest_ensure_minimum(self):
        method = 'smallest:ensure-minimum'
        schema = {
            'test': {
                'width': 120,
                'height': 120,
                'save_optimize': True,
                'format': 'PNG',
                'constraint-method': method,
            },
        }

        # what do we expect ?
        expected_original_wh = (1200, 1600)
        expected_resized_wh = (120, 160)

        r = imagehelper.resizer.Resizer()
        results = r.resize(imagefile=get_imagefile(), resizesSchema=schema, selected_resizes=('test', ), optimize_original=False, optimize_resized=True)

        # what do we have ?
        actual_original_wh = (results.original.width, results.original.height)
        actual_resized_wh = (results.resized['test'].width, results.resized['test'].height)

        # assert the original matches
        assert expected_original_wh[0] == actual_original_wh[0]
        assert expected_original_wh[1] == actual_original_wh[1]

        # assert the resize matches
        assert expected_resized_wh[0] == actual_resized_wh[0]
        assert expected_resized_wh[1] == actual_resized_wh[1]

    def test_fit_within_exact_no_resize(self):
        method = 'exact:no-resize'
        schema = {
            'test': {
                'width': 1200,
                'height': 1600,
                'save_optimize': True,
                'format': 'PNG',
                'constraint-method': method,
            },
        }

        # what do we expect ?
        expected_original_wh = (1200, 1600)
        expected_resized_wh = (1200, 1600)

        r = imagehelper.resizer.Resizer()
        results = r.resize(imagefile=get_imagefile(), resizesSchema=schema, selected_resizes=('test', ), optimize_original=False, optimize_resized=True)

        # what do we have ?
        actual_original_wh = (results.original.width, results.original.height)
        actual_resized_wh = (results.resized['test'].width, results.resized['test'].height)

        # assert the original matches
        assert expected_original_wh[0] == actual_original_wh[0]
        assert expected_original_wh[1] == actual_original_wh[1]

        # assert the resize matches
        assert expected_resized_wh[0] == actual_resized_wh[0]
        assert expected_resized_wh[1] == actual_resized_wh[1]

    def test_fit_within_exact_proportion(self):
        method = 'exact:proportion'
        schema = {
            'test': {
                'width': 240,
                'height': 320,
                'save_optimize': True,
                'format': 'PNG',
                'constraint-method': method,
            },
        }

        # what do we expect ?
        expected_original_wh = (1200, 1600)
        expected_resized_wh = (240, 320)

        r = imagehelper.resizer.Resizer()
        results = r.resize(imagefile=get_imagefile(), resizesSchema=schema, selected_resizes=('test', ), optimize_original=False, optimize_resized=True)

        # what do we have ?
        actual_original_wh = (results.original.width, results.original.height)
        actual_resized_wh = (results.resized['test'].width, results.resized['test'].height)

        # assert the original matches
        assert expected_original_wh[0] == actual_original_wh[0]
        assert expected_original_wh[1] == actual_original_wh[1]

        # assert the resize matches
        assert expected_resized_wh[0] == actual_resized_wh[0]
        assert expected_resized_wh[1] == actual_resized_wh[1]
