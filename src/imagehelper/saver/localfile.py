import logging

log = logging.getLogger(__name__)

# stdlib
import os

# local
from .. import _io
from .. import errors
from .. import utils
from . import _core
from .utils import check_archive_original
from .utils import size_to_filename


# ==============================================================================


class SaverConfig(object):
    """
    Configuration for a localfile saving implementation

    we will save to a `filedir`
    """

    subdir_public_name = None
    subdir_archive_name = None
    archive_original = None
    filedir = None

    def __init__(
        self,
        subdir_public_name=None,
        subdir_archive_name=None,
        archive_original=None,
        filedir="localfile-output",
    ):
        self.subdir_public_name = subdir_public_name
        self.subdir_archive_name = subdir_archive_name
        self.archive_original = archive_original
        self.filedir = filedir


class SaverLogger(_core.SaverLogger):
    """
    Abstract interface for logging saves.
    This should be subclassed and provided to a factory
    """

    def log_save(
        self,
        subdir_name=None,
        filename=None,
        file_size=None,
        file_md5=None,
        filepath=None,
    ):
        """
        kwargs:
            subdir_name : name of the subdirectory
            filename : name of the file
            file_size : size of the file in bytes
            file_md5 : md5 value of the file (hex)
            filepath : full filepath for the save. this may be relative but must include the directory above `subdir`
        """
        pass

    def log_delete(self, subdir_name=None, filename=None, filepath=None):
        """
        kwargs:
            subdir_name : name of the subdirectory
            filename : name of the file
            filepath : full filepath for the save. this may be relative but must include the directory above `subdir`
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

    def manager(self):
        """generate and return a new SaverManager instance"""
        return SaverManager(
            saverConfig=self._saverConfig,
            saverLogger=self._saverLogger,
            resizerConfig=self._resizerConfig,
        )

    def simple_access(self):
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

    filename_template = "%(guid)s-%(suffix)s.%(format)s"
    filename_template_archive = "%(guid)s.%(format)s"

    def files_delete(self, files_saved, dry_run=False, remove_empty_dirs=True):
        """does not actually delete"""
        for size in list(files_saved.keys()):

            # grab the stash
            (target_filename, subdir_name) = files_saved[size]

            target_dirname = os.path.join(self._saverConfig.filedir, subdir_name)
            if not os.path.exists(target_dirname):
                raise ValueError("Directory %s does not exist!" % target_dirname)
            target_filepath = os.path.join(target_dirname, target_filename)

            # delete it
            log.debug("going to delete %s " % (target_filepath,))

            if not dry_run:

                os.unlink(target_filepath)

                # external logging
                if self._saverLogger:
                    self._saverLogger.log_delete(
                        subdir_name=subdir_name,
                        filename=target_filename,
                        filepath=target_filepath,
                    )

                # cleanup path
                if remove_empty_dirs:
                    if len(os.listdir(target_dirname)) == 0:
                        os.rmdir(target_dirname)

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
        if not resizerConfig:
            raise ValueError(
                """`SaverManager` requires a `resizerConfig` which contains the resize recipes. these are needed for generating filenames."""
            )
        self._saverConfig = saverConfig
        self._saverLogger = saverLogger
        self._resizerConfig = resizerConfig

    def _validate__selected_resizes(self, resizerResultset, selected_resizes):
        """
        shared validation
        returns: `dict` selected_resizes
        """

        # default to the resized images
        if selected_resizes is None:
            selected_resizes = list(resizerResultset.resized.keys())

        for k in selected_resizes:
            if k not in resizerResultset.resized:
                raise errors.ImageError_ConfigError(
                    "selected size is not resizerResultset.resized (%s)" % k
                )

            if k not in self._resizerConfig.resizesSchema:
                raise errors.ImageError_ConfigError(
                    "selected size is not self._resizerConfig.resizesSchema (%s)" % k
                )

            # exist early for invalid sizes
            if k[0] == "@":
                raise errors.ImageError_ConfigError(
                    "@ is a reserved initial character for image sizes (%s)" % k
                )

        return selected_resizes

    def generate_filenames(
        self, resizerResultset, guid, selected_resizes=None, archive_original=None
    ):
        """
        generates the filenames s3 would save to;
        this is useful for planning/testing or deleting old files

        Returns a `dict` of target filenames:
            keys = resized size
            values = tuple (target_filename, subdir)
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

            # figure out the subdir
            subdir_name = self._saverConfig.subdir_public_name
            if "subdir_public" in instructions:
                subdir_name = instructions["subdir_public"]

            filename_mapping[size] = (target_filename, subdir_name)

        if check_archive_original(resizerResultset, archive_original=archive_original):
            filename_template_archive = self.filename_template_archive
            target_filename = filename_template_archive % {
                "guid": guid,
                "format": utils.PIL_type_to_standardized(
                    resizerResultset.original.format
                ),
            }
            subdir_name = self._saverConfig.subdir_archive_name
            filename_mapping["@archive"] = (target_filename, subdir_name)

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
        Returns a `dict` of resized images
        calls `self.register_image_file()`` if needed
        """
        if guid is None:
            raise errors.ImageError_ArgsError(
                """You must supply a `guid` for
            the image. this is used"""
            )

        # quickly validate
        selected_resizes = self._validate__selected_resizes(
            resizerResultset, selected_resizes
        )

        # and then we have the bucketed filenames...
        target_filenames = self.generate_filenames(
            resizerResultset,
            guid,
            selected_resizes=selected_resizes,
            archive_original=archive_original,
        )

        # log uploads for removal/tracking and return
        _saves = {}
        try:

            # and then we upload...
            for size in selected_resizes:

                (_filename, subdir_name) = target_filenames[size]
                target_dirname = os.path.join(self._saverConfig.filedir, subdir_name)
                if not os.path.exists(target_dirname):
                    os.makedirs(target_dirname)
                target_file = os.path.join(target_dirname, _filename)
                log.debug("Saving %s to %s " % (_filename, target_file))

                if not dry_run:
                    # upload
                    try:
                        # so in py2 we are cStringIO.StringO
                        # but in py3 we are tempfile.SpooledTemporaryFile
                        with open(target_file, _io.FileWriteArgs) as _fh:
                            _fh.write(resizerResultset.resized[size].file.getvalue())

                    except Exception as exc:
                        log.debug(
                            "encountered unexpected exception `%s` in `saver.localfile.SaverManager.files_save`",
                            exc,
                        )
                        raise

                    # log to external plugin too
                    if self._saverLogger:
                        self._saverLogger.log_save(
                            subdir_name=subdir_name,
                            filename=_filename,
                            file_size=resizerResultset.resized[size].file_size,
                            file_md5=resizerResultset.resized[size].file_md5,
                            filepath=target_file,
                        )

                # log for removal/tracking & return
                _saves[size] = (_filename, subdir_name)

            if "@archive" in target_filenames:

                size = "@archive"
                (_filename, subdir_name) = target_filenames[size]
                target_dirname = os.path.join(self._saverConfig.filedir, subdir_name)
                if not os.path.exists(target_dirname):
                    os.makedirs(target_dirname)
                target_file = os.path.join(target_dirname, _filename)
                log.debug("Saving %s to %s " % (_filename, target_file))

                if not dry_run:
                    # upload
                    with open(target_file, _io.FileWriteArgs) as _fh:
                        _fh.write(resizerResultset.original.file.getvalue())

                    # log to external plugin too
                    if self._saverLogger:
                        self._saverLogger.log_save(
                            subdir_name=subdir_name,
                            filename=_filename,
                            file_size=resizerResultset.original.file_size,
                            file_md5=resizerResultset.original.file_md5,
                            filepath=target_file,
                        )

                # log for removal/tracking & return
                _saves[size] = (_filename, subdir_name)

        except Exception as exc:
            # if we have ANY issues, we want to delete everything from amazon s3. otherwise this stuff is just hiding up there
            log.debug(
                "Error uploading... rolling back s3 items. unexpected exception `%s` in `saver.localfile.SaverManager.files_save`",
                exc,
            )
            _saves = self.files_delete(_saves)
            raise errors.ImageError_SaverUpload("error uploading")

        return _saves


class SaverSimpleAccess(_SaverCoreManager):
    def __init__(self, saverConfig=None, saverLogger=None, resizerConfig=None):
        self._saverConfig = saverConfig
        self._saverLogger = saverLogger
        self._resizerConfig = resizerConfig

    def file_save(self, subdir_name, filename, wrappedFile, dry_run=False):

        _saves = {}
        try:
            target_dirname = os.path.join(self._saverConfig.filedir, subdir_name)
            if not os.path.exists(target_dirname):
                os.makedirs(target_dirname)
            target_file = os.path.join(target_dirname, filename)
            log.debug("Saving %s to %s " % (filename, target_file))

            if not dry_run:
                # upload
                with open(target_file, _io.FileWriteArgs) as _fh:
                    _fh.write(wrappedFile.file.getvalue())

                # log to external plugin too
                if self._saverLogger:
                    self._saverLogger.log_save(
                        subdir_name=subdir_name,
                        filename=filename,
                        file_size=wrappedFile.file_size,
                        file_md5=wrappedFile.file_md5,
                        filepath=target_file,
                    )

            # log for removal/tracking & return
            _saves = self.simple_saves_mapping(subdir_name, filename)

            return _saves
        except Exception as exc:
            log.debug(
                "encountered unexpected exception `%s` in `saver.localfile.SaverSimpleAccess.files_save`",
                exc,
            )
            raise

    def simple_saves_mapping(self, subdir_name, filename):
        _saves = {}
        _saves["%s||%s" % (subdir_name, filename)] = (filename, subdir_name)
        return _saves
