import logging
log = logging.getLogger(__name__)

from imagehelper import errors
from imagehelper import utils
from .utils import *
from . import _core

import os


# ==============================================================================


class SaverConfig(object):
    """Configuration for a localfile saving implementation

        we will save to a `filedir`
    """
    key_public = None
    key_private = None
    bucket_public_name = None
    bucket_archive_name = None
    bucket_public_headers = None
    bucket_archive_headers = None
    archive_original = None
    filedir = None

    def __init__(
        self,
        key_public = None,
        key_private = None,
        bucket_public_name = None,
        bucket_archive_name = None,
        bucket_public_headers = None,
        bucket_archive_headers = None,
        archive_original = None,
        filedir = 'localfile-output',
    ):
        self.key_public = key_public
        self.key_private = key_private
        self.bucket_public_name = bucket_public_name
        self.bucket_archive_name = bucket_archive_name
        self.bucket_public_headers = bucket_public_headers
        self.bucket_archive_headers = bucket_archive_headers
        self.archive_original = archive_original
        self.filedir = filedir


class SaverLogger(_core.SaverLogger):

    def log_save(self, bucket_name=None, key=None, file_size=None, file_md5=None, ):
        pass

    def log_delete(self, bucket_name=None, key=None):
        pass


class SaverManagerFactory(object):
    """Factory for generating SaverManager instances"""
    _resizerConfig = None
    _saverConfig = None
    _saverLogger = None

    def __init__(self, saverConfig=None, saverLogger=None, resizerConfig=None):
        self._saverConfig = saverConfig
        self._saverLogger = saverLogger
        self._resizerConfig = resizerConfig

    def manager(self):
        """generate and return a new SaverManager instance"""
        return SaverManager(saverConfig=self._saverConfig, saverLogger=self._saverLogger, resizerConfig=self._resizerConfig)

    def simple_access(self):
        """generate and return a new SaverSimpleAccess instance"""
        return SaverSimpleAccess(saverConfig=self._saverConfig, saverLogger=self._saverLogger, resizerConfig=self._resizerConfig)


class _SaverCoreManager(object):

    _resizerConfig = None
    _saverConfig = None
    _saverLogger = None
    _s3_buckets = None

    filename_template = "%(guid)s-%(suffix)s.%(format)s"
    filename_template_archive = "%(guid)s.%(format)s"

    @property
    def s3_buckets(self):
        """property that memoizes the s3 buckets"""
        if self._s3_buckets is None:
            # memoize the buckets

            # create our bucket list
            s3_buckets = {}

            # @public and @archive are special
            s3_buckets['@public'] = self._saverConfig.bucket_public_name
            if self._saverConfig.bucket_archive_name:
                s3_buckets['@archive'] = self._saverConfig.bucket_archive_name

            # look through our selected sizes
            if self._resizerConfig:
                for size in self._resizerConfig.selected_resizes:
                    if size[0] == "@":
                        raise errors.ImageError_ConfigError("@ is a reserved initial character for image sizes")

                    if 's3_bucket_public' in self._resizerConfig.resizesSchema[size]:
                        bucket_name = self._resizerConfig.resizesSchema[size]['s3_bucket_public']
                        if bucket_name not in s3_buckets:
                            s3_buckets[bucket_name] = bucket_name

            # store the buckets
            self._s3_buckets = s3_buckets

        # return the memoized buckets
        return self._s3_buckets

    def files_delete(self, files):
        """does not actually delete"""
        return []


class SaverManager(_SaverCoreManager):
    """`SaverManager` handles all the actual uploading and deleting"""

    def __init__(self, saverConfig=None, saverLogger=None, resizerConfig=None):
        if not resizerConfig:
            raise ValueError("""`SaverManager` requires a `resizerConfig` which contains the resize recipes. these are needed for generating filenames.""")
        self._saverConfig = saverConfig
        self._saverLogger = saverLogger
        self._resizerConfig = resizerConfig

    def _validate__selected_resizes(self, resizerResultset, selected_resizes):
        """shared validation
            returns `dict` selected_resizes
        """

        # default to the resized images
        if selected_resizes is None:
            selected_resizes = resizerResultset.resized.keys()

        for k in selected_resizes:
            if k not in resizerResultset.resized:
                raise errors.ImageError_ConfigError("selected size is not resizerResultset.resized (%s)" % k)

            if k not in self._resizerConfig.resizesSchema:
                raise errors.ImageError_ConfigError("selected size is not self._resizerConfig.resizesSchema (%s)" % k)

            # exist early for invalid sizes
            if (k[0] == "@"):
                raise errors.ImageError_ConfigError("@ is a reserved initial character for image sizes (%s)" % k)

        return selected_resizes

    def generate_filenames(self, resizerResultset, guid, selected_resizes=None, archive_original=None):
        """
            generates the filenames s3 would save to;
            this is useful for planning/testing or deleting old files

            Returns a `dict` of target filenames
                keys = resized size
                values = tuple (target_filename, bucket_name)
        """
        if guid is None:
            raise errors.ImageError_ArgsError("""You must supply a `guid` for
            the image. this is used for filename templating""")

        # default to the resized images
        if selected_resizes is None:
            selected_resizes = resizerResultset.resized.keys()

        # quickly validate
        selected_resizes = self._validate__selected_resizes(
            resizerResultset, selected_resizes)

        # init our return dict
        filename_mapping = {}

        for size in selected_resizes:

            instructions = self._resizerConfig.resizesSchema[size]

            # calc vars for filename templating
            filename_template = self.filename_template
            suffix = size
            if 'filename_template' in instructions:
                filename_template = instructions['filename_template']
            if 'suffix' in instructions:
                suffix = instructions['suffix']

            _format = instructions['format']
            if _format.lower() in ('auto', 'original', ):
                # if we used a FakeResultSet to generate the filenames, then the resized will be a string of the suffix
                if not isinstance(resizerResultset.resized[size], str):
                    _format = resizerResultset.resized[size].format
                else:
                    _format = resizerResultset.resized[size]

            # generate the filename
            target_filename = filename_template % {
                'guid': guid,
                'suffix': suffix,
                'format': utils.PIL_type_to_standardized(_format)
            }

            # figure out the bucketname
            bucket_name = self._saverConfig.bucket_public_name
            if 's3_bucket_public' in instructions:
                bucket_name = instructions['s3_bucket_public']

            filename_mapping[size] = (target_filename, bucket_name)

        if check_archive_original(resizerResultset, archive_original=archive_original):
            filename_template_archive = self.filename_template_archive
            target_filename = filename_template_archive % {
                'guid': guid,
                'format': utils.PIL_type_to_standardized(resizerResultset.original.format)
            }
            bucket_name = self._saverConfig.bucket_archive_name
            filename_mapping["@archive"] = (target_filename, bucket_name)

        # return the filemapping
        return filename_mapping

    def files_save(self, resizerResultset, guid, selected_resizes=None, archive_original=None):
        """
            Returns a dict of resized images
            calls self.register_image_file() if needed
        """
        if guid is None:
            raise errors.ImageError_ArgsError("""You must supply a `guid` for
            the image. this is used""")

        # quickly validate
        selected_resizes = self._validate__selected_resizes(
            resizerResultset, selected_resizes)

        # and then we have the bucketed filenames...
        target_filenames = self.generate_filenames(
            resizerResultset,
            guid,
            selected_resizes=selected_resizes,
            archive_original=archive_original
        )

        # log uploads for removal/tracking and return
        _saves = {}
        try:

            # and then we upload...
            for size in selected_resizes:

                (_filename, bucket_name) = target_filenames[size]
                target_dirname = os.path.join(self._saverConfig.filedir, bucket_name)
                if not os.path.exists(target_dirname):
                    os.makedirs(target_dirname)
                target_file = os.path.join(target_dirname, _filename)
                log.debug("Saving %s to %s " % (_filename, target_file))

                # upload
                open(target_file, 'w').write(resizerResultset.resized[size].file.getvalue())

                # log for removal/tracking & return
                _saves[size] = (_filename, bucket_name)

                # log to external plugin too
                if self._saverLogger:
                    self._saverLogger.log_save(
                        bucket_name = bucket_name,
                        key = _filename,
                        file_size = resizerResultset.resized[size].file_size,
                        file_md5 = resizerResultset.resized[size].file_md5,
                    )

            if '@archive' in target_filenames:

                size = "@archive"
                (_filename, bucket_name) = target_filenames[size]
                target_dirname = os.path.join(self._saverConfig.filedir, bucket_name)
                if not os.path.exists(target_dirname):
                    os.makedirs(target_dirname)
                target_file = os.path.join(target_dirname, _filename)
                log.debug("Saving %s to %s " % (_filename, target_file))

                # upload
                open(target_file, 'w').write(resizerResultset.original.file.getvalue())

                # log for removal/tracking & return
                _saves[size] = (_filename, bucket_name)

                # log to external plugin too
                if self._saverLogger:
                    self._saverLogger.log_save(
                        bucket_name = bucket_name,
                        key = _filename,
                        file_size = resizerResultset.original.file_size,
                        file_md5 = resizerResultset.original.file_md5,
                    )

        except Exception as e:
            # if we have ANY issues, we want to delete everything from amazon s3. otherwise this stuff is just hiding up there
            log.debug("Error uploading... rolling back s3 items")
            _saves = self.files_delete(_saves)
            raise
            raise errors.ImageError_SaverUpload('error uploading')

        return _saves


class SaverSimpleAccess(_SaverCoreManager):

    def __init__(self, saverConfig=None, saverLogger=None, resizerConfig=None):
        self._saverConfig = saverConfig
        self._saverLogger = saverLogger
        self._resizerConfig = resizerConfig

    def file_save(self, bucket_name, filename, wrappedFile, upload_type="public"):
        if upload_type not in ("public", "archive"):
            raise ValueError("upload_type must be `public` or `archive`")

        _saves = {}
        try:
            target_dirname = os.path.join(self._saverConfig.filedir, bucket_name)
            if not os.path.exists(target_dirname):
                os.makedirs(target_dirname)
            target_file = os.path.join(target_dirname, filename)
            log.debug("Saving %s to %s " % (filename, target_file))

            # upload
            open(target_file, 'w').write(resizerResultset.resized[size].file.getvalue())

            # log for removal/tracking & return
            _uploads = self.simple_saves_mapping(bucket_name, filename)

            # log to external plugin too
            if self._saverLogger:
                self._saverLogger.log_save(
                    bucket_name = bucket_name,
                    key = filename,
                    file_size = wrappedFile.file_size,
                    file_md5 = wrappedFile.file_md5,
                )

            return _saves
        except:
            raise

    def simple_saves_mapping(self, bucket_name, filename):
        _saves = {}
        _saves["%s||%s" % (bucket_name, filename, )] = (filename, bucket_name)
        return _saves
