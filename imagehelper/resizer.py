import logging
log = logging.getLogger(__name__)

# stdlib
from . import errors
from . import image_wrapper
from . import utils

# PyPi
try:
    from PIL import Image
except ImportError:
    raise ValueError('')


# ==============================================================================


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
    resizesSchema = None
    selected_resizes = None
    optimize_original = None
    original_allow_animated = None
    optimize_resized = None

    def __init__(
        self, resizesSchema=None, selected_resizes=None,
        is_subclass=False, optimize_original=None, optimize_resized=None,
        original_allow_animated=None
    ):
        if not is_subclass:
            self.resizesSchema = resizesSchema
            self.optimize_original = optimize_original
            self.optimize_resized = optimize_resized
            self.original_allow_animated = original_allow_animated

            # we want a unique list
            if selected_resizes is None:
                if resizesSchema is not None:
                    selected_resizes = list(resizesSchema.keys())
            else:
                selected_resizes = selected_resizes[:]
            self.selected_resizes = list(set(selected_resizes)) if selected_resizes else None


class ResizerFactory(object):
    """This is a conveniece Factory to store application configuration
    options.

    You can create a single ResizerFactory in your application, then
    just use it to continually resize images.  Factories have no state, they
    simply hold configuration information, so they're threadsafe.
    """
    resizerConfig = None

    def __init__(self, resizerConfig=None):
        """
        args
            `resizerConfig`
                a resizer.ResizerConfig instance
        """
        self.resizerConfig = resizerConfig

    def resizer(self, imagefile=None, file_b64=None):
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
    resized = None
    original = None

    def __init__(self, resized, original=None):
        self.resized = resized
        self.original = original


class Resizer(object):
    """Resizer is our workhorse.
    It stores the image file, the metadata, and the various resizes."""
    _resizerConfig = None
    _resizerResultset = None
    _image = None

    def __init__(self, resizerConfig=None):
        self._resizerConfig = resizerConfig
        self._resizerResultset = None
        self._wrappedImage = None

    def register_image_file(
        self,
        imagefile = None,
        imageWrapper = None,
        file_b64 = None,
        optimize_original = None,
    ):
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
            raise errors.ImageError_DuplicateAction("We already have registered a file.")

        if (imagefile is None) and (imageWrapper is None) and (file_b64 is None):
            raise errors.ImageError_ConfigError("Must submit either imagefile /or/ imageWrapper /or/ file_b64")

        if (imagefile is not None) and (imageWrapper is not None) and (file_b64 is not None):
            raise errors.ImageError_ConfigError("Submit only imagefile /or/ imageWrapper /or/ file_b64")

        if file_b64 is not None:
            imagefile = utils.b64_decode_to_file(file_b64)

        if imagefile is not None:
            self._wrappedImage = image_wrapper.ImageWrapper(imagefile = imagefile)

        elif imageWrapper is not None:
            if not isinstance(imageWrapper, image_wrapper.ImageWrapper):
                raise errors.ImageError_ConfigError("imageWrapper must be of type `imaage_wrapper.ImageWrapper`")
            self._wrappedImage = imageWrapper

        if optimize_original is None:
            if self._resizerConfig:
                optimize_original = self._resizerConfig.optimize_original
            else:
                raise ValueError("no optimize_original and no self._resizerConfig")

        if optimize_original:
            # call a standardized interface
            self.optimize_original()

    def optimize_original(self):
        """standardized inferface for optimizing"""
        log.debug("Resizer.optimize_original")
        self._wrappedImage.basicImage.optimize()

    def resize(
        self,
        imagefile = None,
        imageWrapper = None,
        file_b64 = None,
        resizesSchema = None,
        selected_resizes = None,
        optimize_original = None,
        optimize_resized = None,
        original_allow_animated = None,
    ):
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

        if not len(resizesSchema.keys()):
            raise errors.ImageError_ConfigError("We have no resizesSchema...  error")

        if not len(selected_resizes):
            raise errors.ImageError_ConfigError("We have no selected_resizes...  error")

        if (imagefile is not None) or (imageWrapper is not None) or (file_b64 is not None):
            self.register_image_file(imagefile=imagefile,
                                     imageWrapper=imageWrapper,
                                     file_b64=file_b64,
                                     optimize_original=optimize_original,
                                     )
        else:
            if optimize_original:
                self.optimize_original()

        if not self._wrappedImage:
            raise errors.ImageError_ConfigError("Please pass in a `imagefile` if you have not set an imageFileObject yet")

        # we'll stash the items here
        resized = {}
        for size in selected_resizes:
            if size[0] == "@":
                raise errors.ImageError_ConfigError("@ is a reserved initial character for image sizes")

            # ImageWrapper.resize returns a ResizedImage that has attributes `.resized_image`, `image_format`
            resized[size] = self._wrappedImage.resize(resizesSchema[size])
            if optimize_resized:
                resized[size].optimize()

        resizerResultset = ResizerResultset(
            resized = resized,
            original = self._wrappedImage.get_original(),
        )
        self._resizerResultset = resizerResultset

        return resizerResultset

    def fake_resize(self, original_filename, selected_resizes=None):

        if not self._resizerConfig:
            raise ValueError("fake_resultset requires an instance configured with resizerConfig")
        resizesSchema = self._resizerConfig.resizesSchema

        if selected_resizes is None:
            selected_resizes = self._resizerConfig.selected_resizes

        if not len(resizesSchema.keys()):
            raise errors.ImageError_ConfigError("We have no resizesSchema...  error")

        if not len(selected_resizes):
            raise errors.ImageError_ConfigError("We have no selected_resizes...  error")

        # we'll stash the items here
        resized = {}
        _original_format = (original_filename.split('.'))[-1]
        for size in selected_resizes:
            if size[0] == "@":
                raise errors.ImageError_ConfigError("@ is a reserved initial character for image sizes")
            _format = resizesSchema[size]['format']
            _format = utils.derive_output_format(_format, _original_format)
            resized[size] = _format

        resizerResultset = ResizerResultset(
            resized = resized,
            original = image_wrapper.FakedOriginal(original_filename = original_filename),
        )
        self._resizerResultset = resizerResultset

        return resizerResultset

    def get_original(self):
        """get the original image, which may have data for us"""
        return self._wrappedImage.get_original()
