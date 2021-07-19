import logging

log = logging.getLogger(__name__)

from .. import errors
from .. import utils
from .utils import check_archive_original
from .utils import size_to_filename
from . import _core

try:
    import boto3
except ImportError:
    boto3 = None


class NoBoto(ImportError):
    pass


NO_BOTO = NoBoto("`boto3` was not available for import")


# ==============================================================================


# note: dirty workaround for boto3
"""
boto3 has an absurd flaw in which fileobjects are closed when uploaded
(see https://github.com/boto/s3transfer/issues/80)

This is a temporary workaround
"""

from io import BufferedReader
from io import RawIOBase
from .._compat import PY2


class NonCloseableBufferedReader(BufferedReader):

    """
    # PY3 Typing;

    from typing import Any
    from typing import IO
    from typing import cast

    def __init__(self, raw: IO[bytes], *args: Any, **kwargs: Any):
       super().__init__(cast(RawIOBase, raw), *args, **kwargs)

    def close(self) -> None:
       self.flush()

    """

    def __init__(self, raw, *args, **kwargs):
        if PY2:
            super(NonCloseableBufferedReader, self).__init__(raw, *args, **kwargs)
        else:
            super().__init__(raw, *args, **kwargs)

    def close(self):
        self.flush()


# ==============================================================================


class SaverConfig(object):
    """
    Configuration data for Amazon S3 Services
    """

    key_public = None
    key_private = None
    bucket_public_name = None
    bucket_archive_name = None
    boto3_ExtraArgs_default_public = None
    boto3_ExtraArgs_default_archive = None
    archive_original = None

    def __init__(
        self,
        key_public=None,
        key_private=None,
        bucket_public_name=None,
        bucket_archive_name=None,
        boto3_ExtraArgs_default_public=None,
        boto3_ExtraArgs_default_archive=None,
        archive_original=None,
        **kwargs
    ):
        self.key_public = key_public
        self.key_private = key_private
        self.bucket_public_name = bucket_public_name
        self.bucket_archive_name = bucket_archive_name
        self.boto3_ExtraArgs_default_public = boto3_ExtraArgs_default_public
        self.boto3_ExtraArgs_default_archive = boto3_ExtraArgs_default_archive
        self.archive_original = archive_original

        # v0.6.0 removed this options
        # raise Exceptions to catch incompatibilities; remove in future release
        if ("bucket_public_headers" in kwargs) or ("bucket_archive_headers" in kwargs):
            raise ValueError(
                """`bucket_public_headers` and `bucket_archive_headers` were """
                """removed in v0.6.0. Please update to use """
                """`boto3_ExtraArgs_default_public` and """
                """`boto3_ExtraArgs_default_archive`."""
            )


class SaverLogger(_core.SaverLogger):
    """The s3 save method will log to this logger on uploads and deletes.
    Any object offering these methods can be replaced;
    This is only illustrative."""

    def log_save(self, bucket_name=None, key=None, file_size=None, file_md5=None):
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
        return SaverManager(
            saverConfig=self._saverConfig,
            saverLogger=self._saverLogger,
            resizerConfig=self._resizerConfig,
        )

    def saver_simple_access(self):
        """generate and return a new SaverSimpleAccess instance"""
        return SaverSimpleAccess(
            saverConfig=self._saverConfig,
            saverLogger=self._saverLogger,
            resizerConfig=self._resizerConfig,
        )


class _SaverCoreManager(object):
    """
    based on interface defined in `_core.SaverCoreManager`
    """

    _resizerConfig = None
    _saverConfig = None
    _saverLogger = None
    _s3_client = None
    _s3_bucketnames = None
    _boto3_ExtraArgs_default_public = None
    _boto3_ExtraArgs_default_archive = None

    filename_template = "%(guid)s-%(suffix)s.%(format)s"
    filename_template_archive = "%(guid)s.%(format)s"

    def __init__(self, saverConfig=None, saverLogger=None, resizerConfig=None):
        self._saverConfig = saverConfig
        self._saverLogger = saverLogger
        self._resizerConfig = resizerConfig
        self._generate_defaults()

    def _generate_defaults(self):
        """
        generate the default headers
        """

        # public and archive get different acls / content-types
        self._boto3_ExtraArgs_default_public = {"ACL": "public-read"}
        self._boto3_ExtraArgs_default_archive = {}

        if self._saverConfig.boto3_ExtraArgs_default_public:
            for (k, v) in self._saverConfig.boto3_ExtraArgs_default_public.items():
                self._boto3_ExtraArgs_default_public[k] = v
        if self._saverConfig.boto3_ExtraArgs_default_archive:
            for (k, v) in self._saverConfig.boto3_ExtraArgs_default_archive.items():
                self._boto3_ExtraArgs_default_archive[k] = v

    @property
    def s3_client(self):
        """property that memoizes the connection"""
        if self._s3_client is None:
            if boto3 is None:
                raise NO_BOTO
            self._s3_client = boto3.client(
                "s3",
                aws_access_key_id=self._saverConfig.key_public,
                aws_secret_access_key=self._saverConfig.key_private,
            )
        return self._s3_client

    @property
    def s3_bucketnames(self):
        """property that memoizes the calcuated s3 s3_bucketnames"""
        if self._s3_bucketnames is None:
            if boto3 is None:
                raise NO_BOTO

            # memoize the buckets

            # create our bucket list
            s3_bucketnames = {}

            # @public and @archive are special
            bucketname_public = self._saverConfig.bucket_public_name
            bucketname_archive = self._saverConfig.bucket_archive_name

            s3_bucketnames[bucketname_public] = bucketname_public
            s3_bucketnames["@public"] = bucketname_public
            if self._saverConfig.bucket_archive_name:
                s3_bucketnames[bucketname_archive] = bucketname_archive
                s3_bucketnames["@archive"] = bucketname_archive

            # look through our selected sizes
            if self._resizerConfig:
                for size in self._resizerConfig.selected_resizes:
                    if size[0] == "@":
                        raise errors.ImageError_ConfigError(
                            "@ is a reserved initial character for image sizes"
                        )

                    if "s3_bucket_public" in self._resizerConfig.resizesSchema[size]:
                        bucket_name = self._resizerConfig.resizesSchema[size][
                            "s3_bucket_public"
                        ]
                        if bucket_name not in s3_bucketnames:
                            s3_bucketnames[bucket_name] = bucket_name

            # store the buckets
            self._s3_bucketnames = s3_bucketnames

        # return the memoized buckets
        return self._s3_bucketnames

    def files_delete(self, files_saved, dry_run=False):
        """workhorse for deletion

        `files_saved`
            `dict`
            format =
                files_saved[size] = (target_filename, bucket_name)

        `dry_run`
            default = `False`
            should we just pretend to save?
        """

        # preload the calculated s3 bucketnames
        s3_bucketnames = self.s3_bucketnames

        # convert to a list, because we delete the items from the dict
        for size in list(files_saved.keys()):

            # grab the stash
            (target_filename, _bucket_name) = files_saved[size]

            # get the calculated bucket_name
            bucket_name = s3_bucketnames[_bucket_name]

            # delete it
            log.debug("going to delete `%s` from `%s`" % (target_filename, bucket_name))

            if not dry_run:
                _del_dicts = [
                    {"Key": target_filename},
                ]
                response = self.s3_client.delete_objects(
                    Bucket=bucket_name,
                    Delete={"Objects": _del_dicts},
                )

                # external logging
                if self._saverLogger:
                    self._saverLogger.log_delete(
                        bucket_name=bucket_name, key=target_filename
                    )

            # internal cleanup
            del files_saved[size]

        return files_saved


class SaverManager(_SaverCoreManager):
    """
    `SaverManager` handles all the actual uploading and deleting

    based on interface defined in `_core._SaverCoreManager`
    but inherits from this file's '`_SaverCoreManager`
    """

    def __init__(self, saverConfig=None, saverLogger=None, resizerConfig=None):
        super(SaverManager, self).__init__(
            saverConfig=saverConfig,
            saverLogger=saverLogger,
            resizerConfig=resizerConfig,
        )
        if not resizerConfig:
            raise ValueError(
                """`SaverManager` requires a `resizerConfig` which contains the resize recipes. these are needed for generating filenames."""
            )

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
                raise errors.ImageError_ConfigError(
                    "selected size is not resizerResultset.resized (`%s`)" % k
                )

            if k not in self._resizerConfig.resizesSchema:
                raise errors.ImageError_ConfigError(
                    "selected size is not self._resizerConfig.resizesSchema (`%s`)" % k
                )

            # exist early for invalid sizes
            if k[0] == "@":
                raise errors.ImageError_ConfigError(
                    "@ is a reserved initial character for image sizes (`%s`)" % k
                )

        return selected_resizes

    def generate_filenames(
        self, resizerResultset, guid, selected_resizes=None, archive_original=None
    ):
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
            raise errors.ImageError_ArgsError(
                """You must supply a `guid` for
            the image. this is used for filename templating"""
            )

        # default to the resized images
        if selected_resizes is None:
            selected_resizes = list(resizerResultset.resized.keys())

        # quickly validate
        selected_resizes = self._validate__selected_resizes(
            resizerResultset, selected_resizes
        )

        # init our return dict
        filename_mapping = {}

        for size in selected_resizes:

            instructions = self._resizerConfig.resizesSchema[size]
            target_filename = size_to_filename(
                guid, size, resizerResultset, self.filename_template, instructions
            )

            # figure out the bucket_name
            bucket_name = self._saverConfig.bucket_public_name
            if "s3_bucket_public" in instructions:
                bucket_name = instructions["s3_bucket_public"]

            filename_mapping[size] = (target_filename, bucket_name)

        if check_archive_original(resizerResultset, archive_original=archive_original):
            filename_template_archive = self.filename_template_archive
            target_filename = filename_template_archive % {
                "guid": guid,
                "format": utils.PIL_type_to_standardized(
                    resizerResultset.original.format
                ),
            }
            bucket_name = self._saverConfig.bucket_archive_name
            filename_mapping["@archive"] = (target_filename, bucket_name)

        # return the filemapping
        return filename_mapping

    def files_save(
        self,
        resizerResultset,
        guid,
        selected_resizes=None,
        archive_original=None,
        dry_run=False,
    ):
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
        if boto3 is None:
            raise NO_BOTO

        if guid is None:
            raise errors.ImageError_ArgsError(
                """You must supply a `guid` for
            the image. this is used"""
            )

        # quickly validate
        selected_resizes = self._validate__selected_resizes(
            resizerResultset, selected_resizes
        )

        # preload the calculated s3 bucketnames
        s3_bucketnames = self.s3_bucketnames

        # and then we have the bucketed filenames...
        target_filenames = self.generate_filenames(
            resizerResultset,
            guid,
            selected_resizes=selected_resizes,
            archive_original=archive_original,
        )

        # log uploads for removal/tracking and return
        files_saved = {}
        try:

            # and then we upload...
            for size in selected_resizes:

                # grab the stash
                (target_filename, _bucket_name) = target_filenames[size]

                # get the calculated bucket_name
                bucket_name = s3_bucketnames[_bucket_name]

                log.debug("Uploading `%s` to `%s` " % (target_filename, bucket_name))

                # generate the ExtraArgs
                _boto3_ExtraArgs = self._boto3_ExtraArgs_default_public.copy()
                _boto3_ExtraArgs["ContentType"] = utils.PIL_type_to_content_type(
                    resizerResultset.resized[size].format
                )
                # overwrite with Resizer ExtraArgs
                if "boto3_ExtraArgs" in self._resizerConfig.resizesSchema[size]:
                    for k in self._resizerConfig.resizesSchema[size]["boto3_ExtraArgs"]:
                        _boto3_ExtraArgs[k] = self._resizerConfig.resizesSchema[size][
                            "boto3_ExtraArgs"
                        ][k]

                if not dry_run:
                    # the active file
                    _wrapped = resizerResultset.resized[size]

                    # dirty workaround. boto3 has a bug in which it closes files.
                    _buffer = NonCloseableBufferedReader(_wrapped.file)

                    # upload
                    response = self.s3_client.upload_fileobj(
                        _buffer,
                        bucket_name,
                        target_filename,
                        ExtraArgs=_boto3_ExtraArgs,
                    )
                    _buffer.detach()

                    # log to external plugin too
                    if self._saverLogger:
                        self._saverLogger.log_save(
                            bucket_name=bucket_name,
                            key=target_filename,
                            file_size=_wrapped.file_size,
                            file_md5=_wrapped.file_md5,
                        )

                # log for removal/tracking & return
                files_saved[size] = (target_filename, bucket_name)

            if "@archive" in target_filenames:

                size = "@archive"
                (target_filename, _bucket_name) = target_filenames[size]
                # get the calculated bucket_name
                bucket_name = s3_bucketnames[_bucket_name]

                log.debug("Uploading `%s` to `%s` " % (target_filename, bucket_name))

                # calculate the headers ;
                # no need to set acl, its going to be owner-only by default
                _boto3_ExtraArgs = self._boto3_ExtraArgs_default_archive.copy()
                _boto3_ExtraArgs["ContentType"] = utils.PIL_type_to_content_type(
                    resizerResultset.original.format
                )

                if not dry_run:
                    # the active file
                    _wrapped = resizerResultset.original

                    # dirty workaround. boto3 has a bug in which it closes files.
                    _buffer = NonCloseableBufferedReader(_wrapped.file)

                    # upload
                    response = self.s3_client.upload_fileobj(
                        _buffer,
                        bucket_name,
                        target_filename,
                        ExtraArgs=_boto3_ExtraArgs,
                    )
                    _buffer.detach()

                    # log to external plugin too
                    if self._saverLogger:
                        self._saverLogger.log_save(
                            bucket_name=bucket_name,
                            key=target_filename,
                            file_size=_wrapped.file_size,
                            file_md5=_wrapped.file_md5,
                        )

                # log for removal/tracking & return
                files_saved[size] = (target_filename, bucket_name)

        except Exception as exc:
            # if we have ANY issues, we want to delete everything from amazon s3. otherwise this stuff is just hiding up there
            log.debug(
                "Error uploading... rolling back s3 items. encounted `%s` in `saver.s3.SaverManager.files_save`",
                exc,
            )
            files_saved = self.files_delete(files_saved)
            raise errors.ImageError_S3Upload("error uploading")

        return files_saved


class SaverSimpleAccess(_SaverCoreManager):
    def __init__(self, saverConfig=None, saverLogger=None, resizerConfig=None):
        super(SaverSimpleAccess, self).__init__(
            saverConfig=saverConfig,
            saverLogger=saverLogger,
            resizerConfig=resizerConfig,
        )

    def file_save(
        self, bucket_name, filename, wrappedFile, upload_type="public", dry_run=False
    ):
        if upload_type not in ("public", "archive"):
            raise ValueError("upload_type must be `public` or `archive`")

        if boto3 is None:
            raise NO_BOTO

        # preload the calculated s3 bucketnames
        s3_bucketnames = self.s3_bucketnames

        files_saved = {}
        try:

            # get the calculated bucket_name
            bucket_name = s3_bucketnames[bucket_name]

            log.debug("Uploading `%s` to `%s` " % (filename, bucket_name))

            # calculate the headers ;
            # no need to set acl, its going to be owner-only by default
            _boto3_ExtraArgs = self._boto3_ExtraArgs_default_public.copy()
            _boto3_ExtraArgs["ContentType"] = utils.PIL_type_to_content_type(
                wrappedFile.format
            )

            if not dry_run:

                # dirty workaround. boto3 has a bug in which it closes files.
                _buffer = NonCloseableBufferedReader(wrappedFile.file)

                # upload
                response = self.s3_client.upload_fileobj(
                    _buffer,
                    bucket_name,
                    filename,
                    ExtraArgs=_boto3_ExtraArgs,
                )
                _buffer.detach()

                # log to external plugin too
                if self._saverLogger:
                    self._saverLogger.log_save(
                        bucket_name=bucket_name,
                        key=filename,
                        file_size=wrappedFile.file_size,
                        file_md5=wrappedFile.file_md5,
                    )

            # log for removal/tracking & return
            files_saved = self.simple_saves_mapping(bucket_name, filename)

            return files_saved
        except Exception as exc:
            log.debug(
                "encountered unexpected exception `%s` in `saver.s3.SaverSimpleAccess.files_save`",
                exc,
            )
            raise

    def simple_saves_mapping(self, bucket_name, filename):
        files_saved = {}
        files_saved["`%s`||`%s`" % (bucket_name, filename)] = (filename, bucket_name)
        return files_saved
