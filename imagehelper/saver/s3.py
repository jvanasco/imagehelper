import logging
log = logging.getLogger(__name__)

from imagehelper import errors
from imagehelper import utils
from .utils import *
from . import _core

try:
    import boto
    import boto.s3
    import boto.s3.bucket
except ImportError:
    boto = None


class NoBoto(ImportError):
    pass


NO_BOTO = NoBoto("`boto` was not available for import")


# ==============================================================================


class SaverConfig(object):
    """Configuration info for amazon s3 services"""
    key_public = None
    key_private = None
    bucket_public_name = None
    bucket_archive_name = None
    bucket_public_headers = None
    bucket_archive_headers = None
    archive_original = None

    def __init__(
        self,
        key_public = None,
        key_private = None,
        bucket_public_name = None,
        bucket_archive_name = None,
        bucket_public_headers = None,
        bucket_archive_headers = None,
        archive_original = None,
    ):
        self.key_public = key_public
        self.key_private = key_private
        self.bucket_public_name = bucket_public_name
        self.bucket_archive_name = bucket_archive_name
        self.bucket_public_headers = bucket_public_headers
        self.bucket_archive_headers = bucket_archive_headers
        self.archive_original = archive_original


class SaverLogger(_core.SaverLogger):
    """The s3 save method will log to this logger on uploads and deletes.
    Any object offering these methods can be replaced;
    This is only illustrative."""

    def log_save(self, bucket_name=None, key=None, file_size=None, file_md5=None, ):
        """args:
        `self`
        `bucket_name`
            s3 bucket name
        `key`
            key in bucket
        `file_size`
            size in bytes
        `file_md5`
            hexdigest
        """
        pass

    def log_delete(self, bucket_name=None, key=None):
        """args:
        `self`
        `bucket_name`
            s3 bucket name
        `key`
            key in bucket
        """
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

    def saver_manager(self):
        """generate and return a new SaverManager instance"""
        return SaverManager(saverConfig=self._saverConfig, saverLogger=self._saverLogger, resizerConfig=self._resizerConfig)

    def saver_simple_access(self):
        """generate and return a new SaverSimpleAccess instance"""
        return SaverSimpleAccess(saverConfig=self._saverConfig, saverLogger=self._saverLogger, resizerConfig=self._resizerConfig)


class _SaverCoreManager(object):

    _resizerConfig = None
    _saverConfig = None
    _saverLogger = None
    _s3Connection = None
    _s3_buckets = None

    s3headers_public_default = None
    s3headers_archive_default = None

    filename_template = "%(guid)s-%(suffix)s.%(format)s"
    filename_template_archive = "%(guid)s.%(format)s"

    @property
    def s3_connection(self):
        """property that memoizes the connection"""
        if self._s3Connection is None:
            if boto is None:
                raise NO_BOTO
            self._s3Connection = boto.connect_s3(self._saverConfig.key_public, self._saverConfig.key_private)
        return self._s3Connection

    @property
    def s3_buckets(self):
        """property that memoizes the s3 buckets"""
        if self._s3_buckets is None:
            if boto is None:
                raise NO_BOTO

            # memoize the buckets

            # create our bucket list
            s3_buckets = {}

            # @public and @archive are special
            bucket_public = boto.s3.bucket.Bucket(connection=self.s3_connection, name=self._saverConfig.bucket_public_name)
            s3_buckets[self._saverConfig.bucket_public_name] = bucket_public
            s3_buckets['@public'] = bucket_public
            if self._saverConfig.bucket_archive_name:
                bucket_archive = boto.s3.bucket.Bucket(connection=self.s3_connection, name=self._saverConfig.bucket_archive_name)
                s3_buckets[self._saverConfig.bucket_archive_name] = bucket_archive
                s3_buckets['@archive'] = bucket_archive

            # look through our selected sizes
            if self._resizerConfig:
                for size in self._resizerConfig.selected_resizes:
                    if size[0] == "@":
                        raise errors.ImageError_ConfigError("@ is a reserved initial character for image sizes")

                    if 's3_bucket_public' in self._resizerConfig.resizesSchema[size]:
                        bucket_name = self._resizerConfig.resizesSchema[size]['s3_bucket_public']
                        if bucket_name not in s3_buckets:
                            s3_buckets[bucket_name] = boto.s3.bucket.Bucket(connection=self.s3_connection, name=bucket_name)

            # store the buckets
            self._s3_buckets = s3_buckets

        # return the memoized buckets
        return self._s3_buckets

    def files_delete(self, files_saved, dry_run=False, ):
        """workhorse for deletion

            `files_saved`
                `dict`
                format =
                    files_saved[size] = (target_filename, bucket_name)

            `dry_run`
                default = `False`
                should we just pretend to save?
        """

        # setup the s3 connection
        s3_buckets = self.s3_buckets

        # convert to a list, because we delete the items from the dict
        for size in list(files_saved.keys()):

            # grab the stash
            (target_filename, bucket_name) = files_saved[size]

            # active bucket
            bucket = s3_buckets[bucket_name]

            # delete it
            log.debug("going to delete %s from %s" %
                      (target_filename, bucket_name))

            if not dry_run:
                bucket.delete_key(target_filename)

                # external logging
                if self._saverLogger:
                    self._saverLogger.log_delete(
                        bucket_name=bucket_name,
                        key=target_filename,
                    )

            # internal cleanup
            del files_saved[size]

        return files_saved


class SaverManager(_SaverCoreManager):
    """`SaverManager` handles all the actual uploading and deleting"""

    def __init__(self, saverConfig=None, saverLogger=None, resizerConfig=None):
        if not resizerConfig:
            raise ValueError("""`SaverManager` requires a `resizerConfig` which contains the resize recipes. these are needed for generating filenames.""")
        self._saverConfig = saverConfig
        self._saverLogger = saverLogger
        self._resizerConfig = resizerConfig

        # ##
        # generate the default headers
        # ##
        # public and archive get different acls / content-types
        self.s3headers_public_default = {'x-amz-acl': 'public-read'}
        if self._saverConfig.bucket_public_headers:
            for k in self._saverConfig.bucket_public_headers:
                self.s3headers_public_default[k] = self._saverConfig.bucket_public_headers[k]
        self.s3headers_archive_default = {}
        if self._saverConfig.bucket_archive_headers:
            for k in self._saverConfig.bucket_archive_headers:
                self.s3headers_archive_default[k] = self._saverConfig.bucket_archive_headers[k]

    def _validate__selected_resizes(self, resizerResultset, selected_resizes):
        """shared validation
            returns `dict` selected_resizes

        ARGS
            `resizerResultset`
                `resizer.ResizerResultset` object
                    `resized` - dict of images that were resized
                    `original ` - original file

            `selected_resizes`
                iterable of selected resizes

        """

        # default to the resized images
        if selected_resizes is None:
            selected_resizes = list(resizerResultset.resized.keys())

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

            `resizerResultset`
                a `resizer.ResizerResultset` object
                    `resized` - dict of images that were resized
                    `original ` - original file

            `guid`
                a `uuid` or similar name that forms the basis for storage
                the guid is passed into the template in self._resizerConfig

            `selected_resizes`
                default = `None` -- all keys of resizerResultset.resized
                a `list` of keys to save
                we default to saving all the resized images

            `archive_original`
                default = `None`
                should we archive the original ?
                implicit/explicit archival option.  see `def check_archive_original`

        """
        if guid is None:
            raise errors.ImageError_ArgsError("""You must supply a `guid` for
            the image. this is used for filename templating""")

        # default to the resized images
        if selected_resizes is None:
            selected_resizes = list(resizerResultset.resized.keys())

        # quickly validate
        selected_resizes = self._validate__selected_resizes(
            resizerResultset, selected_resizes)

        # init our return dict
        filename_mapping = {}

        for size in selected_resizes:

            instructions = self._resizerConfig.resizesSchema[size]
            target_filename = size_to_filename(guid, size, resizerResultset, self.filename_template, instructions, )

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

    def files_save(self, resizerResultset, guid, selected_resizes=None, archive_original=None, dry_run=False):
        """
            Returns a dict of resized images
            calls self.register_image_file() if needed

            this resizes the images.
            it returns the images and updates the internal dict.

            `resizerResultset`
                a `resizer.ResizerResultset` object
                    `resized` - dict of images that were resized
                    `original ` - original file

            `guid`
                a `uuid` or similar name that forms the basis for storage
                the guid is passed to the template in `self.generate_filenames`

            `selected_resizes`
                default = `None` -- all keys of resizerResultset.resized
                a `list` of keys to save
                we default to saving all the resized images
                if you don't want to resize any images:
                    pass in an empty list -- []
                    passing in `None` will run the default images

            `archive_original`
                default = `None`
                should we archive the original ?
                implicit/explicit archival option.  see `def check_archive_original`

            `dry_run`
                default = `False`
                should we just pretend to upload
        """
        if boto is None:
            raise NO_BOTO

        if guid is None:
            raise errors.ImageError_ArgsError("""You must supply a `guid` for
            the image. this is used""")

        # quickly validate
        selected_resizes = self._validate__selected_resizes(
            resizerResultset, selected_resizes)

        # setup the s3 connection
        s3_buckets = self.s3_buckets

        # and then we have the bucketed filenames...
        target_filenames = self.generate_filenames(
            resizerResultset,
            guid,
            selected_resizes=selected_resizes,
            archive_original=archive_original
        )

        # log uploads for removal/tracking and return
        files_saved = {}
        try:

            # and then we upload...
            for size in selected_resizes:

                (target_filename, bucket_name) = target_filenames[size]
                bucket = s3_buckets[bucket_name]

                log.debug("Uploading %s to %s " % (target_filename, bucket))

                # generate the headers
                _s3_headers = self.s3headers_public_default.copy()
                _s3_headers['Content-Type'] = utils.PIL_type_to_content_type(resizerResultset.resized[size].format)
                if 's3_headers' in self._resizerConfig.resizesSchema[size]:
                    for k in self._resizerConfig.resizesSchema[size]['s3_headers']:
                        _s3_headers[k] = self._resizerConfig.resizesSchema[size]['s3_headers'][k]

                if not dry_run:
                    # upload
                    s3_key = boto.s3.key.Key(bucket)
                    s3_key.key = target_filename
                    s3_key.set_contents_from_string(resizerResultset.resized[size].file.getvalue(), headers=_s3_headers)

                    # log to external plugin too
                    if self._saverLogger:
                        self._saverLogger.log_save(
                            bucket_name = bucket_name,
                            key = target_filename,
                            file_size = resizerResultset.resized[size].file_size,
                            file_md5 = resizerResultset.resized[size].file_md5,
                        )

                # log for removal/tracking & return
                files_saved[size] = (target_filename, bucket_name)

            if '@archive' in target_filenames:

                size = "@archive"
                (target_filename, bucket_name) = target_filenames[size]
                bucket = s3_buckets[bucket_name]

                log.debug("Uploading %s to %s " % (target_filename, bucket_name))

                # calculate the headers ;
                # no need to set acl, its going to be owner-only by default
                _s3_headers = self.s3headers_archive_default.copy()
                _s3_headers['Content-Type'] = utils.PIL_type_to_content_type(resizerResultset.original.format)

                if not dry_run:
                    # upload
                    s3_key_original = boto.s3.key.Key(bucket)
                    s3_key_original.key = target_filename
                    s3_key_original.set_contents_from_string(resizerResultset.original.file.getvalue(), headers=_s3_headers)

                    # log to external plugin too
                    if self._saverLogger:
                        self._saverLogger.log_save(
                            bucket_name = bucket_name,
                            key = target_filename,
                            file_size = resizerResultset.original.file_size,
                            file_md5 = resizerResultset.original.file_md5,
                        )

                # log for removal/tracking & return
                files_saved[size] = (target_filename, bucket_name)

        except Exception as e:
            # if we have ANY issues, we want to delete everything from amazon s3. otherwise this stuff is just hiding up there
            log.debug("Error uploading... rolling back s3 items")
            files_saved = self.files_delete(files_saved)
            raise
            raise errors.ImageError_S3Upload('error uploading')

        return files_saved


class SaverSimpleAccess(_SaverCoreManager):

    def __init__(self, saverConfig=None, saverLogger=None, resizerConfig=None):
        self._saverConfig = saverConfig
        self._saverLogger = saverLogger
        self._resizerConfig = resizerConfig

        # ##
        # ## generate the default headers
        # ##
        # public and archive get different acls / content-types
        self.s3headers_public_default = {'x-amz-acl': 'public-read'}
        if self._saverConfig.bucket_public_headers:
            for k in self._saverConfig.bucket_public_headers:
                self.s3headers_public_default[k] = self._saverConfig.bucket_public_headers[k]
        self.s3headers_archive_default = {}
        if self._saverConfig.bucket_archive_headers:
            for k in self._saverConfig.bucket_archive_headers:
                self.s3headers_archive_default[k] = self._saverConfig.bucket_archive_headers[k]

    def file_save(self, bucket_name, filename, wrappedFile, upload_type="public", dry_run=False, ):
        if upload_type not in ("public", "archive"):
            raise ValueError("upload_type must be `public` or `archive`")

        if boto is None:
            raise NO_BOTO

        s3_buckets = self.s3_buckets
        files_saved = {}
        try:

            bucket = s3_buckets[bucket_name]

            log.debug("Uploading %s to %s " % (filename, bucket_name))

            # calculate the headers ;
            # no need to set acl, its going to be owner-only by default
            _s3_headers = self.s3headers_public_default.copy()
            _s3_headers['Content-Type'] = utils.PIL_type_to_content_type(wrappedFile.format)

            if not dry_run:
                # upload
                s3_key_original = boto.s3.key.Key(bucket)
                s3_key_original.key = filename
                s3_key_original.set_contents_from_string(wrappedFile.file.getvalue(), headers=_s3_headers)

                # log to external plugin too
                if self._saverLogger:
                    self._saverLogger.log_save(
                        bucket_name = bucket_name,
                        key = filename,
                        file_size = wrappedFile.file_size,
                        file_md5 = wrappedFile.file_md5,
                    )

            # log for removal/tracking & return
            files_saved = self.simple_saves_mapping(bucket_name, filename)

            return files_saved
        except:
            raise

    def simple_saves_mapping(self, bucket_name, filename):
        files_saved = {}
        files_saved["%s||%s" % (bucket_name, filename, )] = (filename, bucket_name)
        return files_saved
