# stdlib
import logging
import os
from pathlib import Path
import tempfile
from typing import Dict
from typing import Optional

# local
from . import _core
from .utils import check_archive_original
from .utils import size_to_filename
from .. import _io
from .. import errors
from .. import utils
from .._types import TYPE_files_mapping
from ..image_wrapper import BasicImage
from ..image_wrapper import ResizerInstructions
from ..resizer import ResizerConfig
from ..resizer import ResizerResultset
from ..resizer import TYPE_selected_resizes


# ==============================================================================

log = logging.getLogger(__name__)


class ResizerInstructions_Localfile(ResizerInstructions):
    subdir_public: str


TYPE_ResizesSchema_Localfile = Dict[str, ResizerInstructions_Localfile]


class ResizerConfig_Localfile(ResizerConfig):
    resizesSchema: TYPE_ResizesSchema_Localfile  # type: ignore[assignment]


# ------------------------------------------------------------------------------


class SaverConfig(_core.SaverConfig):
    """
    Configuration for a localfile saving implementation

    we will save to a `filedir`
    """

    subdir_public_name: str
    subdir_archive_name: str
    filedir: str
    archive_original: Optional[bool] = None

    def __init__(
        self,
        subdir_public_name: str = "public",
        subdir_archive_name: str = "archive",
        filedir: str = "localfile-output",
        archive_original: Optional[bool] = None,
    ):
        self.subdir_public_name = subdir_public_name
        self.subdir_archive_name = subdir_archive_name
        self.filedir = filedir
        self.archive_original = archive_original


class SaverLogger(_core.SaverLogger):
    """
    Abstract interface for logging saves.
    This should be subclassed and provided to a factory
    """

    def log_save(  # type: ignore[override]
        self,
        subdir_name: Optional[str] = None,
        filename: Optional[str] = None,
        file_size: Optional[int] = None,
        file_md5: Optional[str] = None,
        filepath: Optional[str] = None,
    ) -> None:
        """
        kwargs:
            subdir_name : name of the subdirectory
            filename : name of the file
            file_size : size of the file in bytes
            file_md5 : md5 value of the file (hex)
            filepath : full filepath for the save. this may be relative but must include the directory above `subdir`
        """
        log.debug(
            "<localfile.save> subdir_name: `%s`, filename: `%s`, file_size: `%s`, file_md5: `%s`, filepath: `%s`",
            subdir_name,
            filename,
            file_size,
            file_md5,
            filepath,
        )

    def log_delete(  # type: ignore[override]
        self,
        subdir_name: Optional[str] = None,
        filename: Optional[str] = None,
        filepath: Optional[str] = None,
    ) -> None:
        """
        kwargs:
            subdir_name : name of the subdirectory
            filename : name of the file
            filepath : full filepath for the save. this may be relative but must include the directory above `subdir`
        """
        log.debug(
            "<localfile.delete> subdir_name: `%s`, filename: `%s`, filepath: `%s`",
            subdir_name,
            filename,
            filepath,
        )


class SaverManagerFactory(_core.SaverManagerFactory):
    """Factory for generating SaverManager instances"""

    _resizerConfig: ResizerConfig_Localfile
    _saverConfig: SaverConfig
    _saverLogger: SaverLogger

    def __init__(
        self,
        saverConfig: SaverConfig,
        saverLogger: SaverLogger,
        resizerConfig: ResizerConfig_Localfile,
    ):
        self._saverConfig = saverConfig
        self._saverLogger = saverLogger
        self._resizerConfig = resizerConfig

    def manager(self) -> "SaverManager":
        """generate and return a new SaverManager instance"""
        return SaverManager(
            saverConfig=self._saverConfig,
            saverLogger=self._saverLogger,
            resizerConfig=self._resizerConfig,
        )

    def simple_access(self) -> "SaverSimpleAccess":
        """generate and return a new SaverSimpleAccess instance"""
        return SaverSimpleAccess(
            saverConfig=self._saverConfig,
            saverLogger=self._saverLogger,
            resizerConfig=self._resizerConfig,
        )


class _SaverCoreManager(_core._SaverCoreManager):
    """
    based on interface defined in `_core.SaverCoreManager`
    """

    _resizerConfig: ResizerConfig_Localfile
    _saverConfig: SaverConfig
    _saverLogger: SaverLogger
    filename_template: str = "%(guid)s-%(suffix)s.%(format)s"
    filename_template_archive: str = "%(guid)s.%(format)s"

    def __init__(
        self,
        saverConfig: SaverConfig,
        saverLogger: SaverLogger,
        resizerConfig: ResizerConfig_Localfile,
    ):
        self._saverConfig = saverConfig
        self._saverLogger = saverLogger
        self._resizerConfig = resizerConfig

    def _target_path(self, subdir: str, filename: str) -> str:
        """Resolve a relative destination within the configured storage root."""
        root = Path(self._saverConfig.filedir).resolve()
        directory, name = Path(subdir), Path(filename)
        target = root / directory / name
        resolved = target.resolve()
        if (
            directory.is_absolute()
            or name.is_absolute()
            or ".." in directory.parts
            or ".." in name.parts
            or not name.parts
            or not resolved.is_relative_to(root)
            or resolved == root
        ):
            raise ValueError("Local image destination must be inside the storage root")
        return str(target)

    @staticmethod
    def _write_file(target: str, payload: bytes) -> None:
        """Publish a complete local file using a temporary sibling."""
        fd, temporary = tempfile.mkstemp(dir=os.path.dirname(target))
        try:
            with os.fdopen(fd, _io.FileWriteArgs) as stream:
                stream.write(payload)
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def files_delete(
        self,
        files_saved: TYPE_files_mapping,
        dry_run: bool = False,
        remove_empty_dirs: bool = True,
    ) -> TYPE_files_mapping:
        """Delete mapped local files, or only consume the mapping in a dry run."""
        for size in list(files_saved.keys()):
            # grab the stash
            (target_filename, subdir_name) = files_saved[size]

            target_filepath = self._target_path(subdir_name, target_filename)
            target_dirname = os.path.dirname(target_filepath)
            if not os.path.exists(target_dirname):
                raise ValueError("Directory %s does not exist!" % target_dirname)

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
                if (
                    remove_empty_dirs
                    and Path(target_dirname).resolve()
                    != Path(self._saverConfig.filedir).resolve()
                ):
                    if len(os.listdir(target_dirname)) == 0:
                        os.rmdir(target_dirname)

            # internal cleanup
            del files_saved[size]

        return files_saved


class SaverManager(_SaverCoreManager, _core.SaverManager):
    """
    `SaverManager` handles all the actual uploading and deleting

    based on interface defined in `_core._SaverCoreManager`
    but inherits from this file's '`_SaverCoreManager`
    """

    def __init__(
        self,
        saverConfig: SaverConfig,
        saverLogger: SaverLogger,
        resizerConfig: ResizerConfig_Localfile,
    ):
        if not resizerConfig:
            raise ValueError(
                """`SaverManager` requires a `resizerConfig` which contains the resize recipes. these are needed for generating filenames."""
            )
        self._saverConfig = saverConfig
        self._saverLogger = saverLogger
        self._resizerConfig = resizerConfig

    def _validate__selected_resizes(
        self,
        resizerResultset: ResizerResultset,
        selected_resizes: Optional[TYPE_selected_resizes],
    ) -> TYPE_selected_resizes:
        """
        shared validation
        returns: `LIST` selected_resizes
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
        self,
        resizerResultset: ResizerResultset,
        guid: str,
        selected_resizes: Optional[TYPE_selected_resizes] = None,
        archive_original: Optional[bool] = None,
    ) -> TYPE_files_mapping:
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
            assert resizerResultset.original
            assert resizerResultset.original.format
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

    def files_save(  # type: ignore[override]
        self,
        resizerResultset: ResizerResultset,
        guid: str,
        selected_resizes: Optional[TYPE_selected_resizes] = None,
        archive_original: Optional[bool] = None,
        dry_run: bool = False,
    ) -> TYPE_files_mapping:
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
                target_file = self._target_path(subdir_name, _filename)
                os.makedirs(os.path.dirname(target_file), exist_ok=True)
                log.debug("Saving %s to %s " % (_filename, target_file))

                if not dry_run:
                    self._write_file(
                        target_file, resizerResultset.resized[size].file.getvalue()
                    )

                    _saves[size] = (_filename, subdir_name)

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
                target_file = self._target_path(subdir_name, _filename)
                os.makedirs(os.path.dirname(target_file), exist_ok=True)
                log.debug("Saving %s to %s " % (_filename, target_file))

                if not dry_run:
                    # upload
                    self._write_file(target_file, resizerResultset.original.file.getvalue())

                    _saves[size] = (_filename, subdir_name)

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
            if not dry_run:
                self.files_delete(_saves)
            raise errors.ImageError_SaverUpload("error saving local images") from exc

        return _saves


class SaverSimpleAccess(_SaverCoreManager, _core.SaverSimpleAccess):
    def __init__(
        self,
        saverConfig=None,
        saverLogger=None,
        resizerConfig=None,
    ):
        self._saverConfig = saverConfig
        self._saverLogger = saverLogger
        self._resizerConfig = resizerConfig

    def file_save(  # type: ignore[override]
        self,
        subdir_name: str,
        filename: str,
        wrappedFile: BasicImage,
        dry_run: bool = False,
    ) -> TYPE_files_mapping:
        _saves = {}
        try:
            target_file = self._target_path(subdir_name, filename)
            os.makedirs(os.path.dirname(target_file), exist_ok=True)
            log.debug("Saving %s to %s " % (filename, target_file))

            if not dry_run:
                # upload
                self._write_file(target_file, wrappedFile.file.getvalue())

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

    def simple_saves_mapping(
        self,
        subdir_name,
        filename,
    ) -> TYPE_files_mapping:
        _saves = {}
        _saves["%s||%s" % (subdir_name, filename)] = (filename, subdir_name)
        return _saves
