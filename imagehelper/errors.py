import logging
log = logging.getLogger(__name__)


# ==============================================================================


class ImageError(Exception):
    """Base class for Exceptions"""
    pass


class ImageError_ArgsError(ImageError):
    pass


class ImageError_ConfigError(ImageError):
    pass


class ImageError_DuplicateAction(ImageError):
    pass


class ImageError_MissingFile(ImageError):
    pass


class ImageError_Parsing(ImageError):
    pass


class ImageError_ResizeError(ImageError):
    pass


class ImageError_SaverUpload(ImageError):
    pass


class ImageError_S3Upload(ImageError_SaverUpload):
    pass
