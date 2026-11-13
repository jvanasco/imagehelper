# stdlib
import cgi
import io
import logging
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple
from typing import Union

# pypi
try:
    from PIL import Image
except ImportError:
    raise ImportError("Image library (Pillow) is required")

# local
from . import _io
from . import errors
from . import utils
from ._types import ResizerInstructions

# ==============================================================================

log = logging.getLogger(__name__)


try:
    # PIL.__version__>=9.0.0
    ANTIALIAS = Image.Resampling.LANCZOS
except AttributeError:
    # PIL.__version__<9.0.0
    # py3.6
    ANTIALIAS = Image.ANTIALIAS  # type: ignore [attr-defined]


# import PIL
# _pil_version = PIL.__version__.split(".")
# if int(_pil_version[0]) < 9:
#     # this should only be py36
#     ANTIALIAS = Image.ANTIALIAS
# else:
#     ANTIALIAS = Image.Resampling.LANCZOS


USE_THUMBNAIL: bool = False

_valid_types = [
    cgi.FieldStorage,
    _io._FilelikePreference,
    tempfile.SpooledTemporaryFile,
]
_valid_types.extend(list(_io._CoreFileTypes))
_valid_types_nameless = [_io._FilelikePreference, tempfile.SpooledTemporaryFile]

VALID_TYPES = tuple(_valid_types)
VALID_TYPES_NAMELESS = tuple(_valid_types_nameless)


VALID_CONSTRAINTS = (
    "fit-within",
    "fit-within:crop-to",
    "fit-within:ensure-width",
    "fit-within:ensure-height",
    "smallest:ensure-minimum",
    "exact:no-resize",
    "exact:proportion",
    "passthrough:no-resize",
)


# ------------------------------------------------------------------------------

_OPTIMIZE_SUPPORT_DETECTED: Optional[bool] = None
OPTIMIZE_SUPPORT: Dict = {
    "advpng": {
        "available": None,
        "use": True,
        "options": {"level": 4},  # 4 is max
        "binary": None,
    },
    "gifsicle": {
        "available": None,
        "use": True,
        "options": {"level": 3, "interlace": None},
        "binary": None,
    },
    "jpegtran": {
        "available": None,
        "use": True,
        "options": {"progressive": True},
        "binary": None,
    },
    "jpegoptim": {
        "available": None,
        "use": True,
        "binary": None,
    },
    "optipng": {
        "available": None,
        "use": True,
        "options": {"level": 3},  # 6 would be best
        "binary": None,
    },
    "pngcrush": {
        "available": None,
        "use": True,
        "binary": None,
    },
}


def autodetect_support(
    test_libraries: Optional[List[str]] = None,
) -> None:
    """Check PATH or configured binary paths for the selected optimizers."""
    global _OPTIMIZE_SUPPORT_DETECTED

    libraries = OPTIMIZE_SUPPORT if test_libraries is None else test_libraries
    for library in libraries:
        settings = OPTIMIZE_SUPPORT[library]
        settings["available"] = shutil.which(settings["binary"] or library) is not None
    _OPTIMIZE_SUPPORT_DETECTED = all(
        settings["available"] is not None for settings in OPTIMIZE_SUPPORT.values()
    )


_OPTIMIZER_CHAINS = {
    "jpg": ("jpegtran", "jpegoptim"),
    "gif": ("gifsicle",),
    "png": ("pngcrush", "optipng", "advpng"),
}


def _optimizer_command(name: str, source: Path, output: Path) -> list[str]:
    """Build the argument vector for one isolated optimizer stage."""
    settings = OPTIMIZE_SUPPORT[name]
    binary = settings["binary"] or name
    options = settings.get("options", {})
    if name in ("jpegoptim", "advpng"):
        shutil.copyfile(source, output)
        if name == "jpegoptim":
            return [binary, "--strip-all", "-q", str(output)]
        return [binary, f"-{options['level']}", "-z", str(output)]
    if name == "jpegtran":
        flags = ["-progressive"] if options["progressive"] else []
        return [
            binary, "-copy", "all", "-optimize", *flags,
            "-outfile", str(output), str(source),
        ]
    if name == "gifsicle":
        interlace = options.get("interlace")
        flags = []
        if interlace is not None:
            flags.append("--interlace" if interlace else "--no-interlace")
        return [
            binary, f"-O{options['level']}", *flags,
            "--output", str(output), str(source),
        ]
    if name == "pngcrush":
        return [binary, "-rem", "alla", "-reduce", "-q", str(source), str(output)]
    return [binary, "-i0", f"-o{options['level']}", "-out", str(output), str(source)]


def _validate_optimizer_output(source: Path, output: Path) -> None:
    """Require decodable output with the same format, dimensions, and frame count."""
    with Image.open(source) as original, Image.open(output) as candidate:
        frames = getattr(candidate, "n_frames", 1)
        if (
            candidate.format != original.format
            or candidate.size != original.size
            or frames != getattr(original, "n_frames", 1)
        ):
            raise ValueError("Optimizer changed image format, dimensions, or frame count")
        for frame in range(frames):
            candidate.seek(frame)
            candidate.load()


# ==============================================================================


class BasicImage(object):
    """
    A generic wrapper for Images
    """

    # `file` a file-like object; ie, StringIO
    # file: io.IOBase
    file: io.BytesIO

    # `format`
    format: Optional[str] = None

    # `name`
    name: Optional[str] = None

    # `mode` file attribute
    mode = None

    # `width` file attribute
    width: Optional[int] = None

    # `height` file attribute
    height: Optional[int] = None

    # `None` by default; `True` if `optimize` successful; `False` if it failed
    is_optimized: Optional[bool] = None

    # `None` by default. If `optimize` is run, it becomes a list of external tool + status
    optimizations: Optional[list[tuple[str, bool]]] = None

    def __init__(
        self,
        fileObject: io.BytesIO,
        name: Optional[str] = None,
        format: Optional[str] = None,
        mode=None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        is_image_animated: Optional[bool] = None,
        animated_image_totalframes: Optional[int] = None,
    ):
        """
        :arg fileObject: the resized file
        :param name: default None
        :param format: default None
        :param mode: default None
        :param width: default None
        :param height: default None
        :param is_image_animated: default None
        :param animated_image_totalframes: default None
        """
        self.file = fileObject
        self.file.seek(0)  # be kind, rewind
        self.name = name
        self.format = format
        self.mode = mode
        self.width = width
        self.height = height
        self.optimization_savings = 0
        self.is_image_animated = is_image_animated
        self.animated_image_totalframes = animated_image_totalframes

    @property
    def file_size(self) -> int:
        """property; calculate the file's size in bytes"""
        return utils.file_size(self.file)

    @property
    def file_md5(self) -> str:
        """property; calculate the file's md5"""
        return utils.file_md5(self.file)

    @property
    def file_b64(self) -> bytes:
        """property; base64 encode the file"""
        return utils.file_b64(self.file)

    @property
    def format_standardized(self) -> Optional[str]:
        """proxied format; standardized version"""
        if self.format is None:
            return None
        return utils.PIL_type_to_standardized(self.format)

    @property
    def file_extension(self) -> Optional[str]:
        """proxied format; PIL version"""
        if self.format is None:
            return None
        return utils.PIL_type_to_extension(self.format)

    def optimize(self) -> None:
        """Run the available optimizers and keep the last valid result.

        Failed stages leave the previous result intact. Savings are measured in
        bytes and can be negative when the optimized image is larger.
        """
        chain = _OPTIMIZER_CHAINS.get(self.format_standardized or "")
        if chain is None:
            return
        if not _OPTIMIZE_SUPPORT_DETECTED:
            autodetect_support()

        self.optimizations = []
        self.is_optimized = False
        self.optimization_savings = 0
        self.file.seek(0)
        enabled = [
            name for name in chain
            if OPTIMIZE_SUPPORT[name]["available"] and OPTIMIZE_SUPPORT[name]["use"]
        ]
        if not enabled:
            return

        with tempfile.TemporaryDirectory(prefix="imagehelper-") as directory:
            original = Path(directory) / "source"
            source = original
            try:
                with source.open("wb") as destination:
                    shutil.copyfileobj(self.file, destination)
            finally:
                self.file.seek(0)
            original_size = source.stat().st_size
            for name in enabled:
                output = Path(directory) / name
                try:
                    subprocess.run(
                        _optimizer_command(name, source, output),
                        check=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=60,
                    )
                    _validate_optimizer_output(source, output)
                except (
                    OSError,
                    ValueError,
                    EOFError,
                    Image.DecompressionBombError,
                    subprocess.SubprocessError,
                ) as exc:
                    log.debug("Optimizer %s failed: %s", name, exc)
                    self.optimizations.append((name, False))
                else:
                    source = output
                    self.optimizations.append((name, True))

            if source != original:
                result = _io._FilelikePreference()
                result.write(source.read_bytes())
                result.seek(0)
                self.file = result
                self.is_optimized = True
                self.optimization_savings = original_size - source.stat().st_size


class ResizedImage(BasicImage):
    """A class for a ResizedImage Result."""

    def __repr__(self):
        return "<ReizedImage at %s - %s >" % (id(self), self.__dict__)


class FakedOriginal(BasicImage):
    """sometimes we need to fake an original file"""

    format: str
    mode = None
    width: int
    height: int
    file_size: int
    file_md5: str

    def __init__(self, original_filename: str):
        file_ext = original_filename.split(".")[-1].lower()
        self.format = utils.standardized_to_PIL_type(file_ext)


class FakedResize(BasicImage):
    file: None = None  # type: ignore [assignment]
    format: str
    width: Union[int, None]
    height: Union[int, None]

    def __init__(
        self,
        format: str,
        width: Union[int, None],
        height: Union[int, None],
    ):
        self.format = format
        self.width = width
        self.height = height


def _validate_input_limits(
    max_filesize: Optional[int], max_dimensions: Optional[tuple[int, int]]
) -> None:
    """Reject negative byte limits and nonpositive dimension limits."""
    if max_filesize is not None and max_filesize < 0:
        raise ValueError("max_filesize must be nonnegative")
    if max_dimensions is not None and min(max_dimensions) <= 0:
        raise ValueError("max_dimensions must contain positive width and height")


def _check_input_dimensions(
    size: tuple[int, int], max_dimensions: Optional[tuple[int, int]]
) -> None:
    """Reject images whose width or height exceeds its configured maximum."""
    if max_dimensions is not None and (
        size[0] > max_dimensions[0] or size[1] > max_dimensions[1]
    ):
        raise errors.ImageError_Parsing(utils.ImageErrorCodes.DIMENSIONS_LIMIT_EXCEEDED)


class ImageWrapper(object):
    """Our base class for image operations"""

    basicImage: BasicImage
    pilObject: Image.Image

    def get_original(self) -> BasicImage:
        """Return the original image and its copied file data."""
        return self.basicImage

    def __del__(self) -> None:
        image = getattr(self, "pilObject", None)
        if image is not None:
            image.close()

    def __init__(
        self,
        imagefile: _io.TYPES_imagefile_a,
        imagefile_name: Optional[str] = None,
        FilelikePreference: Optional[_io.TYPES_FilelikeSupported] = None,
        *,
        max_filesize: Optional[int] = None,
        max_dimensions: Optional[tuple[int, int]] = None,
    ) -> None:
        """Copy and validate a binary image stream or CGI file upload.

        Rewind the input after reading and use the explicit name when provided.
        Byte and (width, height) limits are inclusive. Raise ImageError_Parsing
        if a limit is exceeded or the input cannot be loaded as an image.
        """
        _validate_input_limits(max_filesize, max_dimensions)
        if imagefile is None:
            raise errors.ImageError_MissingFile(utils.ImageErrorCodes.MISSING_FILE)

        if not isinstance(imagefile, VALID_TYPES):
            raise errors.ImageError_Parsing(
                utils.ImageErrorCodes.UNSUPPORTED_IMAGE_CLASS
            )

        image_data: Optional[io.BytesIO] = None
        image: Optional[Image.Image] = None
        loaded = False
        try:
            if isinstance(imagefile, cgi.FieldStorage):
                if not hasattr(imagefile, "filename"):
                    raise errors.ImageError_Parsing(
                        utils.ImageErrorCodes.MISSING_FILENAME_METHOD
                    )
                source = imagefile.file
                if source is None:
                    raise errors.ImageError_MissingFile(
                        utils.ImageErrorCodes.MISSING_FILE
                    )
                file_name = getattr(source, "name", imagefile.filename)
            else:
                source = imagefile
                if isinstance(source, VALID_TYPES_NAMELESS):
                    file_name = imagefile_name or ""
                else:
                    file_name = getattr(source, "name", imagefile_name)
                    if file_name == "<fdopen>":
                        file_name = imagefile_name or ""

            source.seek(0)
            try:
                if max_filesize is None:
                    file_data = source.read()
                else:
                    # Check the encoded size before allocating a copy.
                    source.seek(0, io.SEEK_END)
                    if source.tell() > max_filesize:
                        raise errors.ImageError_Parsing(
                            utils.ImageErrorCodes.FILESIZE_LIMIT_EXCEEDED
                        )
                    source.seek(0)
                    file_data = source.read(max_filesize + 1)
                    if len(file_data) > max_filesize:
                        raise errors.ImageError_Parsing(
                            utils.ImageErrorCodes.FILESIZE_LIMIT_EXCEEDED
                        )
            finally:
                source.seek(0)
            if not isinstance(file_data, bytes):
                raise errors.ImageError_Parsing(utils.ImageErrorCodes.INVALID_FILETYPE)

            if FilelikePreference is None:
                FilelikePreference = _io._FilelikePreference
            stream_factory = FilelikePreference
            image_data = stream_factory()
            image_data.write(file_data)
            image_data.seek(0)

            image = Image.open(image_data)
            _check_input_dimensions(image.size, max_dimensions)
            image.load()
            if image.format is None:
                raise errors.ImageError_Parsing(utils.ImageErrorCodes.INVALID_REBUILD)
            self.basicImage = BasicImage(
                image_data,
                name=imagefile_name or file_name,
                format=image.format,
                mode=image.mode,
                width=image.width,
                height=image.height,
                is_image_animated=utils.is_image_animated(image),
                animated_image_totalframes=utils.animated_image_totalframes(image),
            )
            self.pilObject = image
            loaded = True
        except (OSError, Image.DecompressionBombError) as exc:
            raise errors.ImageError_Parsing(
                utils.ImageErrorCodes.INVALID_FILETYPE
            ) from exc
        finally:
            if not loaded:
                try:
                    if image is not None:
                        image.close()
                finally:
                    if image_data is not None and not image_data.closed:
                        image_data.close()

    def resize(
        self,
        instructions_dict: ResizerInstructions,
        FilelikePreference: Optional[_io.TYPES_FilelikeSupported] = None,
    ) -> ResizedImage:
        """this does the heavy lifting

        be warned - this uses a bit of memory!

        1. we operate on a copy of the pilObject via _io.cStringIo
            (which is already a copy of the original)
        2. we save to another new _io 'file'

        valid `constraint-method` for `instructions_dict`

            'fit-within'
                Resizes item to fit within the bounding box, on both height
                and width.   This resulting image will be the size of the
                bounding box or smaller.

            'fit-within:crop-to'
                resizes the item along whichever axis ensures the bounding box
                is 100% full, then crops.  This resulting image will be the
                size of the bounding box.

            'fit-within:ensure-width'
                resizes item to fit within the bounding box, scaling height
                to ensure 100% width.  This resulting image will be the size of
                the bounding box.

            'fit-within:ensure-height'
                resizes item to fit within the bounding box, scaling width to
                ensure 100% height. This resulting image will be the size of
                the bounding box.

            'smallest:ensure-minimum'
                useful for things like og:image where you want at least a 200px
                image.

            'exact:no-resize'
                don't scale! raises an error if a scale must be made. this is a
                convenience for just saving/re-encoding files.
                i.e. 100x100 must receive an image that is 100x100

            'exact:proportion'
                tries to scale the image to an exact size.  raises an error if
                it can't.  Usually this is used to resample a 1:1 image, however
                this might be used to drop an image to a specific proportion.
                i.e. 300x400 can scale to 30x40, 300x400 but not 30x50

            'passthrough:no-resize'
                don't scale!
                for typing support,
                set width and height to `None`

            `FilelikePreference` - default preference for file-like objects
        """
        # mypy typing
        if self.pilObject is None:
            raise ValueError("mising `self.pilObject`")

        if FilelikePreference is None:
            FilelikePreference = _io._FilelikePreference

        # we analyze the pilObject, because `copy()` only works on the frame
        if utils.is_image_animated(self.pilObject):
            allow_animated = False
            if "allow_animated" in instructions_dict:
                allow_animated = instructions_dict["allow_animated"]
            if not allow_animated:
                raise errors.ImageError_InstructionsError(
                    "Image is Animated but instructions do not allow it!"
                )

        resized_image = self.pilObject.copy()

        if resized_image.palette:
            resized_image = resized_image.convert()

        constraint_method = "fit-within"
        if "constraint-method" in instructions_dict:
            constraint_method = instructions_dict["constraint-method"]

        if constraint_method not in VALID_CONSTRAINTS:
            raise ValueError("Invalid constraint_method: `%s`" % constraint_method)

        if constraint_method != "passthrough:no-resize":
            # t_ = target
            # i_ = image / real

            (i_w, i_h) = self.pilObject.size

            t_w = instructions_dict["width"]
            t_h = instructions_dict["height"]

            if (t_w is None) or (t_h is None):
                raise ValueError("`None` is only valid for `passthrough:no-resize`")

            crop: Optional[Tuple[int, int, int, int]] = None
            # type hints for below switch
            proportion: float
            proportion_w: float
            proportion_h: float

            # notice that we only scale DOWN (ie: check that t_x < i_x

            if constraint_method in ("fit-within", "fit-within:crop-to"):
                # figure out the proportions
                proportion_w = 1
                proportion_h = 1
                if t_w < i_w:
                    proportion_w = t_w / i_w
                if t_h < i_h:
                    proportion_h = t_h / i_h

                if constraint_method == "fit-within":
                    # peg to the SMALLEST proportion so the entire image fits
                    if proportion_w < proportion_h:
                        proportion_h = proportion_w
                    elif proportion_h < proportion_w:
                        proportion_w = proportion_h
                    # figure out the resizes!
                    t_w = int(i_w * proportion_w)
                    t_h = int(i_h * proportion_h)

                elif constraint_method == "fit-within:crop-to":
                    # peg so the smallest dimension fills the canvas, then crop the rest.
                    if proportion_w > proportion_h:
                        proportion_h = proportion_w
                    elif proportion_h > proportion_w:
                        proportion_w = proportion_h

                    # note what we want to crop to
                    crop_w = t_w
                    crop_h = t_h

                    # figure out the resizes!
                    t_w = int(i_w * proportion_w)
                    t_h = int(i_h * proportion_h)

                    if (crop_w != t_w) or (crop_h != t_h):
                        # support_hack_against_artifacting handles an issue where .thumbnail makes stuff look like shit
                        # except we're not using .thumbnail anymore; we're using resize directly
                        support_hack_against_artifacting = USE_THUMBNAIL
                        if support_hack_against_artifacting:
                            if t_w < i_w:
                                t_w += 1
                            if t_h < i_h:
                                t_h += 1

                        (x0, y0, x1, y1) = (0, 0, t_w, t_h)

                        if t_w > crop_w:
                            x0 = int((t_w / 2) - (crop_w / 2))
                            x1 = x0 + crop_w

                        if t_h > crop_h:
                            y0 = int((t_h / 2) - (crop_h / 2))
                            y1 = y0 + crop_h

                        crop = (x0, y0, x1, y1)

            elif constraint_method == "fit-within:ensure-width":
                proportion = 1
                if t_w < i_w:
                    proportion = t_w / i_w
                t_h = int(i_h * proportion)

            elif constraint_method == "fit-within:ensure-height":
                proportion = 1
                if t_h < i_h:
                    proportion = t_h / i_h
                t_w = int(i_w * proportion)

            elif constraint_method == "smallest:ensure-minimum":
                # useful for things like og:image where you want at least a 200px image

                # figure out the proportions
                proportion_w = t_w / i_w
                proportion_h = t_h / i_h

                # we don't want to scale up...
                if proportion_h > 1 or proportion_w > 1:
                    proportion_h = 1
                    proportion_w = 1

                # use_scale = "h"
                scale_factor = proportion_h
                if proportion_w > proportion_h:
                    # use_scale = "w"
                    scale_factor = proportion_w

                t_h = int(i_h * scale_factor)
                t_w = int(i_w * scale_factor)

            elif constraint_method == "exact:proportion":
                proportion_w = 1
                proportion_h = 1
                if t_w < i_w:
                    proportion_w = t_w / i_w
                if t_h < i_h:
                    proportion_h = t_h / i_h
                if proportion_w != proportion_h:
                    raise errors.ImageError_ResizeError(
                        "item can not be scaled to exact size"
                    )

            elif constraint_method == "exact:no-resize":
                if (t_w != i_w) or (t_h != i_h):
                    raise errors.ImageError_ResizeError("item is not exact size")

            else:
                raise errors.ImageError_ResizeError(
                    'Invalid constraint-method for size recipe: "%s"'
                    % constraint_method
                )

            if (i_w != t_w) or (i_h != t_h):
                if USE_THUMBNAIL:
                    # the thumbnail is faster, but has been looking uglier in recent versions
                    resized_image.thumbnail((t_w, t_h), ANTIALIAS)
                else:
                    resized_image = resized_image.resize((t_w, t_h), ANTIALIAS)

            if crop:
                resized_image = resized_image.crop(crop)
                resized_image.load()

        format = "JPEG"
        if "format" in instructions_dict:
            format = instructions_dict["format"]

        # returns uppercase
        original_format = self.get_original().format
        assert original_format is not None
        format = utils.derive_format(format, original_format)

        def _get_pil_options(_format: str) -> Dict:
            pil_options: Dict = {}
            if format in ("JPEG", "PDF"):
                for i in ("quality", "optimize", "progressive"):
                    k = "save_%s" % i
                    if k in instructions_dict:
                        pil_options[i] = instructions_dict[k]  # type: ignore[literal-required]
            elif format == "PNG":
                for i in ("optimize", "transparency", "bits", "dictionary"):
                    k = "save_%s" % i
                    if k in instructions_dict:
                        pil_options[i] = instructions_dict[k]  # type: ignore[literal-required]
            return pil_options

        # inner function will generate keys for us
        pil_options = _get_pil_options(format)

        # save the image !
        resized_image_file = FilelikePreference()
        resized_image.save(resized_image_file, format, **pil_options)

        return ResizedImage(
            resized_image_file,
            format=format,
            width=resized_image.size[0],
            height=resized_image.size[1],
        )
