"""
abstracted classes, more like interfaces
"""

import logging
from typing import Optional

# ==============================================================================

from .._types import TYPE_files_mapping
from ..image_wrapper import BasicImage
from ..resizer import ResizerConfig
from ..resizer import ResizerResultset
from ..resizer import TYPE_selected_resizes

# ------------------------------------------------------------------------------

log = logging.getLogger(__name__)


class SaverConfig(object):
    archive_original: Optional[bool] = None


class SaverLogger(object):
    def log_save(self, **kwargs) -> None:
        log.debug("<_core.save> %s", kwargs)

    def log_delete(self, **kwargs) -> None:
        log.debug("<_core.delete> %s", kwargs)


class SaverManagerFactory(object):
    _resizerConfig: ResizerConfig
    _saverConfig: SaverConfig
    _saverLogger: SaverLogger

    def manager(self) -> "SaverManager":  # type: ignore[empty-body]
        pass

    def simple_access(self) -> "SaverSimpleAccess":  # type: ignore[empty-body]
        pass


class _SaverCoreManager(object):
    _resizerConfig: ResizerConfig
    _saverConfig: SaverConfig
    _saverLogger: SaverLogger

    def files_delete(  # type: ignore[empty-body]
        self,
        files_saved: TYPE_files_mapping,
        dry_run: bool = False,
    ) -> TYPE_files_mapping:
        """
        workhorse for deletion

        `files_saved`
            `dict`
            format =
                files_saved[size] = (target_filename, bucket_name)
        """
        pass


class SaverManager(_SaverCoreManager):
    def generate_filenames(  # type: ignore[empty-body]
        self,
        resizerResultset: ResizerResultset,
        guid: str,
        selected_resizes: Optional[TYPE_selected_resizes] = None,
        archive_original: Optional[bool] = None,
    ) -> TYPE_files_mapping:
        pass

    def files_save(  # type: ignore[empty-body]
        self,
        resizerResultset: ResizerResultset,
        guid: str,
        selected_resizes: Optional[TYPE_selected_resizes] = None,
        archive_original: Optional[bool] = None,
        dry_run: Optional[bool] = False,
    ) -> TYPE_files_mapping:
        pass

    # _SaverCoreManager.files_delete


class SaverSimpleAccess(_SaverCoreManager):
    def file_save(  # type: ignore[empty-body]
        self,
        bucket_name: str,
        filename: str,
        wrappedFile: BasicImage,
        upload_type: str = "public",
        dry_run: bool = False,
    ) -> TYPE_files_mapping:
        pass

    def simple_saves_mapping(  # type: ignore[empty-body]
        self,
        bucket_name: str,
        filename: str,
    ) -> TYPE_files_mapping:
        pass

    # _SaverCoreManager.files_delete
