# stdlib
import io
import logging
from typing import Optional

# local
from . import errors
from . import image_wrapper
from . import utils
from ._types import ResizesSchema as TYPE_ResizesSchema
from ._types import TYPE_resizes
from ._types import TYPE_selected_resizes

# ==============================================================================

log = logging.getLogger(__name__)


# ------------------------------------------------------------------------------


class ResizerConfig(object):
    """ResizerFactory allows you to specify what/how to resize.

    You could subclass this configuator - just instantiate the object with
        `is_subclass = True`
    to preserve your vars, or configure one on the fly with __init__()

    `resizesSchema` - a dict in this format:
        {  'size_name': {
                'width': 120,
                'height': 120,
                'constraint-method': 'fit-within',
                'save_quality': 50,
                'filename_template': '%(guid)s.%(format)s',
                'suffix': 't1',
                'format':'JPEG',
            },
            'other_size_name': {...},
        }

    `selected_resizes`: an array of size names (see above) to be resized
        if a list or tuple is supplied, it will be copied.

    width*
        in pixels

    height*
        in pixels

    format
        defaults to JPEG

    constraint-method
        see below for valid constraint methods


    save_
        keys prepended with `save_` are stripped of "save_" and are then
        passed on to PIL as kwargs.
        warning: different formats accept different arguments. view the
        code in 'resize' to see what works.

    valid constraint methods:

        see `imagehelper.image_wrapper.ImageWrapper().resize()` for full
        details

        'exact:no-resize'
        'exact:proportion'
        'fit-within'
        'fit-within:crop-to'
        'fit-within:ensure-height'
        'fit-within:ensure-width'
        'smallest:ensure-minimum'

        `optimize` - True / False

    """

    resizesSchema: TYPE_ResizesSchema
    selected_resizes: TYPE_selected_resizes
    optimize_original: Optional[bool] = None
    optimize_resized: bool = False
    max_filesize: Optional[int] = None
    max_dimensions: Optional[tuple[int, int]] = None
    allow_animated_gif: bool = False
    max_animation_frames: Optional[int] = None
    max_animation_pixels: Optional[int] = None

    def __init__(
        self,
        resizesSchema: Optional[TYPE_ResizesSchema] = None,
        selected_resizes: Optional[TYPE_selected_resizes] = None,
        is_subclass: bool = False,
        optimize_original: Optional[bool] = None,
        optimize_resized: bool = False,
        *,
        max_filesize: Optional[int] = None,
        max_dimensions: Optional[tuple[int, int]] = None,
        allow_animated_gif: bool = False,
        max_animation_frames: Optional[int] = None,
        max_animation_pixels: Optional[int] = None,
    ) -> None:
        """Configure resize recipes and optional inclusive input limits."""
        image_wrapper._validate_input_limits(max_filesize, max_dimensions)
        if not is_subclass or max_filesize is not None:
            self.max_filesize = max_filesize
        if not is_subclass or max_dimensions is not None:
            self.max_dimensions = max_dimensions
        if not is_subclass or allow_animated_gif:
            self.allow_animated_gif = allow_animated_gif
        if not is_subclass or max_animation_frames is not None:
            self.max_animation_frames = max_animation_frames
        if not is_subclass or max_animation_pixels is not None:
            self.max_animation_pixels = max_animation_pixels
        image_wrapper._validate_animation_policy(
            self.allow_animated_gif, self.max_animation_frames, self.max_animation_pixels
        )
        if not is_subclass:
            if resizesSchema:
                self.resizesSchema = resizesSchema
            self.optimize_original = optimize_original
            self.optimize_resized = optimize_resized

            # we want a unique list
            if selected_resizes is None:
                if resizesSchema is not None:
                    selected_resizes = list(resizesSchema.keys())
            else:
                selected_resizes = selected_resizes[:]
            if selected_resizes:
                self.selected_resizes = list(set(selected_resizes))


class ResizerFactory(object):
    """This is a conveniece Factory to store application configuration
    options.

    You can create a single ResizerFactory in your application, then
    just use it to continually resize images.  Factories have no state, they
    simply hold configuration information, so they're threadsafe.
    """

    resizerConfig: ResizerConfig

    def __init__(self, resizerConfig: ResizerConfig):
        """
        args
            `resizerConfig`
                a resizer.ResizerConfig instance
        """
        self.resizerConfig = resizerConfig

    def resizer(
        self,
        imagefile: Optional[io.IOBase] = None,
        file_b64: Optional[bytes] = None,
    ) -> "Resizer":
        """Returns a resizer object; optionally with an imagefile.
        This does not resize.

        This is useful for validating a file for it's ability to be resized.

        args
            `imagefile`
                an object supported by image_wrapper
                usually:
                    file
                    cgi.fi
            `file_b64`
                b64 encoding of the image file. this is to support serialized
                messagebrokers for workers like celery
        """
        resizer = Resizer(resizerConfig=self.resizerConfig)
        if imagefile is not None and file_b64 is not None:
            raise ValueError("Only pass in `imagefile` or `file_b64`")
        if (imagefile is not None) or (file_b64 is not None):
            resizer.register_image_file(imagefile=imagefile, file_b64=file_b64)
        return resizer


class ResizerResultset(object):
    """A resultset contains two attributes:
    .original  - image_wrapper.BasicImage
    .resizes  - dict.  keys = 'sizes', values = image_wrapper.BasicImage
    """

    resized: TYPE_resizes
    original: image_wrapper.BasicImage

    def __init__(self, resized, original=None):
        self.resized = resized
        self.original = original


class Resizer(object):
    """Resizer is our workhorse.
    It stores the image file, the metadata, and the various resizes."""

    _resizerConfig: Optional[ResizerConfig] = None
    _resizerResultset: Optional[ResizerResultset] = None
    _wrappedImage: Optional[image_wrapper.ImageWrapper]

    def __init__(
        self,
        resizerConfig: Optional[ResizerConfig] = None,
    ):
        self._resizerConfig = resizerConfig
        self._resizerResultset = None
        self._wrappedImage = None

    def register_image_file(
        self,
        imagefile=None,
        imageWrapper: Optional[image_wrapper.ImageWrapper] = None,
        file_b64: Optional[bytes] = None,
        optimize_original: Optional[bool] = None,
    ) -> None:
        """
        registers a file to be resized

        if we pass in cgi.FieldStorage, it seems to bool() to None even when there is a value
        the workaround (grr) is to check against None

        args:
            `imagefile`
                the image as a file
            `imageWrapper`
                the image wrapped in a `imagehelper.image_wrapper.ImageWrapper`
            `file_b64`
                b64 encoding of the image file. this is to support serialized
                messagebrokers for workers like celery
        """
        if self._wrappedImage is not None:
            raise errors.ImageError_DuplicateAction(
                "We already have registered a file."
            )

        if sum(value is not None for value in (imagefile, imageWrapper, file_b64)) != 1:
            raise errors.ImageError_ConfigError(
                "Submit exactly one of imagefile, imageWrapper, or file_b64"
            )

        config = self._resizerConfig
        max_filesize = config.max_filesize if config is not None else None
        max_dimensions = config.max_dimensions if config is not None else None
        allow_animated = config.allow_animated_gif if config is not None else False
        max_frames = config.max_animation_frames if config is not None else None
        max_pixels = config.max_animation_pixels if config is not None else None
        image_wrapper._validate_animation_policy(allow_animated, max_frames, max_pixels)

        if file_b64 is not None:
            if max_filesize is not None:
                # Bound decoder allocation. Allow ASCII whitespace used by encodebytes.
                max_encoded = 4 * ((max_filesize + 2) // 3)
                encoded = bytearray()
                for byte in file_b64:
                    if byte not in b" \t\r\n\v\f":
                        if len(encoded) == max_encoded:
                            raise errors.ImageError_Parsing(
                                utils.ImageErrorCodes.FILESIZE_LIMIT_EXCEEDED
                            )
                        encoded.append(byte)
                file_b64 = bytes(encoded)
            with utils.b64_decode_to_file(file_b64) as decoded:
                self._wrappedImage = image_wrapper.ImageWrapper(
                    decoded, max_filesize=max_filesize, max_dimensions=max_dimensions,
                    allow_animated_gif=allow_animated, max_animation_frames=max_frames,
                    max_animation_pixels=max_pixels,
                )
        elif imagefile is not None:
            self._wrappedImage = image_wrapper.ImageWrapper(
                imagefile, max_filesize=max_filesize, max_dimensions=max_dimensions,
                allow_animated_gif=allow_animated, max_animation_frames=max_frames,
                max_animation_pixels=max_pixels,
            )

        elif imageWrapper is not None:
            if not isinstance(imageWrapper, image_wrapper.ImageWrapper):
                raise errors.ImageError_ConfigError(
                    "imageWrapper must be of type `imaage_wrapper.ImageWrapper`"
                )
            original = imageWrapper.get_original()
            if max_filesize is not None and original.file_size > max_filesize:
                raise errors.ImageError_Parsing(
                    utils.ImageErrorCodes.FILESIZE_LIMIT_EXCEEDED
                )
            image_wrapper._check_input_dimensions(
                imageWrapper.pilObject.size, max_dimensions
            )
            if original.is_image_animated:
                frames = original.animated_image_totalframes
                assert frames is not None
                width, height = imageWrapper.pilObject.size
                image_wrapper._check_animation_input(
                    original.format, allow_animated, frames, width * height * frames,
                    max_frames, max_pixels,
                )
            self._wrappedImage = imageWrapper

        if optimize_original is None:
            if self._resizerConfig:
                optimize_original = self._resizerConfig.optimize_original
            else:
                raise ValueError("no optimize_original and no self._resizerConfig")

        if optimize_original:
            # call a standardized interface
            self.optimize_original()

    def optimize_original(self) -> None:
        """standardized inferface for optimizing"""
        log.debug("Resizer.optimize_original")
        assert self._wrappedImage
        self._wrappedImage.basicImage.optimize()

    def resize(
        self,
        imagefile=None,
        imageWrapper: Optional[image_wrapper.ImageWrapper] = None,
        file_b64: Optional[bytes] = None,
        resizesSchema: Optional[TYPE_ResizesSchema] = None,
        selected_resizes: Optional[TYPE_selected_resizes] = None,
        optimize_original: Optional[bool] = None,
        optimize_resized: Optional[bool] = None,
    ) -> ResizerResultset:
        """
        Returns a dict of resized images
        calls self.register_image_file() if needed

        this resizes the images.
        it returns the images and updates the internal dict.

        the internal dict will have an @archive object as well

        args:
            `imagefile`
                the image as a file
            `imageWrapper`
                the image wrapped in a `imagehelper.image_wrapper.ImageWrapper`
            `file_b64`
                b64 encoding of the image file. this is to support serialized
                messagebrokers for workers like celery
        """
        if resizesSchema is None:
            if self._resizerConfig:
                resizesSchema = self._resizerConfig.resizesSchema
            else:
                raise ValueError("no resizesSchema and no self._resizerConfig")
        assert resizesSchema

        if optimize_original is None:
            if self._resizerConfig:
                optimize_original = self._resizerConfig.optimize_original
            else:
                raise ValueError("no optimize_original and no self._resizerConfig")

        if optimize_resized is None:
            if self._resizerConfig:
                optimize_resized = self._resizerConfig.optimize_resized
            else:
                raise ValueError("no optimize_resized and no self._resizerConfig")

        if selected_resizes is None:
            if self._resizerConfig:
                selected_resizes = self._resizerConfig.selected_resizes
            else:
                raise ValueError("no selected_resizes and no self._resizerConfig")
        assert selected_resizes

        if not len(resizesSchema.keys()):
            raise errors.ImageError_ConfigError("We have no resizesSchema...  error")

        if not len(selected_resizes):
            raise errors.ImageError_ConfigError("We have no selected_resizes...  error")

        if (
            (imagefile is not None)
            or (imageWrapper is not None)
            or (file_b64 is not None)
        ):
            self.register_image_file(
                imagefile=imagefile,
                imageWrapper=imageWrapper,
                file_b64=file_b64,
                optimize_original=optimize_original,
            )
        else:
            if optimize_original:
                self.optimize_original()

        if not self._wrappedImage:
            raise errors.ImageError_ConfigError(
                "Please pass in a `imagefile` if you have not set an imageFileObject yet"
            )

        max_pixels = self._resizerConfig.max_animation_pixels if self._resizerConfig else None
        animation_budget = [max_pixels] if max_pixels is not None else None
        resized = {}
        for size in selected_resizes:
            if size[0] == "@":
                raise errors.ImageError_ConfigError(
                    "@ is a reserved initial character for image sizes"
                )

            # ImageWrapper.resize returns a ResizedImage that has attributes `.resized_image`, `image_format`
            resized[size] = self._wrappedImage.resize(
                resizesSchema[size], _animation_budget=animation_budget
            )
            if optimize_resized:
                resized[size].optimize()

        resizerResultset = ResizerResultset(
            resized=resized, original=self._wrappedImage.get_original()
        )
        self._resizerResultset = resizerResultset

        return resizerResultset

    def fake_resize(
        self,
        original_filename: str,
        selected_resizes: Optional[TYPE_selected_resizes] = None,
    ) -> ResizerResultset:
        if not self._resizerConfig:
            raise ValueError(
                "fake_resize requires an instance configured with resizerConfig"
            )
        resizesSchema = self._resizerConfig.resizesSchema
        assert resizesSchema

        if selected_resizes is None:
            selected_resizes = self._resizerConfig.selected_resizes
            assert selected_resizes

        if not len(resizesSchema.keys()):
            raise errors.ImageError_ConfigError("We have no resizesSchema...  error")

        if not len(selected_resizes):
            raise errors.ImageError_ConfigError("We have no selected_resizes...  error")

        # we'll stash the items here
        resized = {}
        _original_format = (original_filename.split("."))[-1]
        for size in selected_resizes:
            if size[0] == "@":
                raise errors.ImageError_ConfigError(
                    "@ is a reserved initial character for image sizes"
                )
            _format = resizesSchema[size]["format"]
            _format = utils.derive_format(_format, _original_format)
            resized[size] = image_wrapper.FakedResize(
                format=_format,
                width=resizesSchema[size]["width"],
                height=resizesSchema[size]["height"],
            )

        resizerResultset = ResizerResultset(
            resized=resized,
            original=image_wrapper.FakedOriginal(original_filename=original_filename),
        )
        self._resizerResultset = resizerResultset

        return resizerResultset

    def get_original(self):
        """get the original image, which may have data for us"""
        if self._wrappedImage is None:
            raise ValueError("No `_wrappedImage` configured")
        return self._wrappedImage.get_original()
