from __future__ import division

import logging
log = logging.getLogger(__name__)

# stdlib
import cgi
import tempfile

# PyPi
import six
try:
    from PIL import Image
except ImportError:
    raise ValueError("Image is required")
import envoy
# from subprocess import call


# local
from . import errors
from . import utils
from . import _io


# ==============================================================================


USE_THUMBNAIL = False

_valid_types = [cgi.FieldStorage,
                _io._CoreFileType,
                _io.StringIO,
                tempfile.SpooledTemporaryFile,
                ]
_valid_types_nameless = [_io.StringIO,
                         tempfile.SpooledTemporaryFile,
                         ]
if _io.cStringIO:
    # this only happens in Python2
    _valid_types.extend((_io.cStringIO.InputType,
                         _io.cStringIO.OutputType,
                         ))
    _valid_types_nameless.extend((_io.cStringIO.InputType,
                                  _io.cStringIO.OutputType,
                                  ))

_valid_types = tuple(_valid_types)
_valid_types_nameless = tuple(_valid_types_nameless)


# ==============================================================================


# these are set to True by imagehelper/__init__.py on import
_OPTIMIZE_SUPPORT_DETECTED = None
OPTIMIZE_SUPPORT = {
    'advpng': {'available': None,
               'use': True,
               'options': {'level': 4,  # 4 is max
                           },
               'binary': None,
               '*autodetect_args': '--help',
               },
    'gifsicle': {'available': None,
                 'use': True,
                 'options': {'level': 3,
                             },
                 'binary': None,
                 '*autodetect_args': '--help',
                 },
    'jpegtran': {'available': None,
                 'use': True,
                 'options': {'progressive': True,
                             },
                 'binary': None,
                 '*autodetect_args': '--help',
                 },
    'jpegoptim': {'available': None,
                  'use': True,
                  'binary': None,
                  '*autodetect_args': '--help',
                  },
    'optipng': {'available': None,
                'use': True,
                'options': {'level': 3,  # 6 would be best
                            },
                'binary': None,
                '*autodetect_args': '--help',
                },
    'pngcrush': {'available': None,
                 'use': True,
                 'binary': None,
                 '*autodetect_args': '--help',
                 },

}


def autodetect_support(test_libraries=None):
    """
    ``test_libraries`` should be a list of keys in the OPTIMIZE_SUPPORT list
    if not supplied, all will be tested
    this only needs to be done once per application
    
    it tests if a program exists by invoking the `help` subcommand for
    each shell command. this runs relatively quickly, but calls multiple
    external programs. Python3 has `shutil.which` but this library supports
    Python2
    
    if you have a forking application, you should run before forking:
    
        import imagehelper
        imagehelper.image_wrapper.autodetect_support()
    
    otherwise, the first invocation of .optimize() will cause this to run
    once run, `_OPTIMIZE_SUPPORT_DETECTED` will be set, blocking further
    autodetections
    """
    log.debug("autodetect_support")
    if test_libraries is None:
        test_libraries = list(OPTIMIZE_SUPPORT.keys())
    for library in test_libraries:
        _binary = OPTIMIZE_SUPPORT[library]['binary'] or library
        result = envoy.run("""%s %s""" % (_binary, OPTIMIZE_SUPPORT[library]['*autodetect_args']))
        if result.status_code == 1:
            log.debug('   available:    %s', library)
            OPTIMIZE_SUPPORT[library]['available'] = True
        elif result.status_code == 127:
            log.debug('!!! unavailable: %s', library)
            OPTIMIZE_SUPPORT[library]['available'] = False
        else:
            log.debug('xxx unsupported code: %s : %s', library, result.status_code)
            # leave None for every other code
    global _OPTIMIZE_SUPPORT_DETECTED
    _OPTIMIZE_SUPPORT_DETECTED = True


# ==============================================================================


class BasicImage(object):
    """A generic wrapper for Images

        `file`
            a filelike object
                ie, cStringIO

        `format`
        `name`

        `mode`
        `width`
        `height`
            resized file attributes

        `file_size`
            property to calculate the file's size

        `file_md5`
            property to calculate the file's md5

    """
    def __init__(
        self,
        fileObject,
        name=None,
        format=None,
        mode=None,
        width=None,
        height=None,
        is_image_animated=None,
        animated_image_totalframes=None,
    ):
        """args
            `resized_file`
                * required
            `format`
            `name`
            `mode`
            `width`
            `height`
                default = None

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

    # `None` by default; `True` if `optimize` successful; `False` if it failed
    is_optimized = None

    # `None` by default. If `optimize` is run, it becomes a list of external tool + status
    optimizations = None

    @property
    def file_size(self):
        """property; calculate the file's size in bytes"""
        return utils.file_size(self.file)

    @property
    def file_md5(self):
        """property; calculate the file's md5"""
        return utils.file_md5(self.file)

    @property
    def file_b64(self):
        """property; base64 encode the file"""
        return utils.file_b64(self.file)

    @property
    def format_standardized(self):
        """proxied format; standardized version"""
        return utils.PIL_type_to_standardized(self.format)

    @property
    def file_extension(self):
        """proxied format; PIL version"""
        return utils.PIL_type_to_extension(self.format)

    def optimize(self, ):
        """this does some heavy lifting

            unix/mac only feature; sorry.

            this function creates an infile and outfile via NamedTemporaryFile
            it then pipes the file through lossless compression options

            this will replace the self.file object
        """
        if self.format_standardized not in ('jpg', 'png', 'gif'):
            return
        log.debug("optimizing a file.  format is: %s" % self.format_standardized)

        FilelikePreference = _io._FallbackFileType
        if _io.cStringIO:
            # only in Python2
            if isinstance(self.file, _io.cStringIO.OutputType):
                FilelikePreference = _io.cStringIO.StringIO

        # we need to write the image onto the disk with an infile and outfile
        # this does suck.
        self.file.seek(0)
        fileInput = tempfile.NamedTemporaryFile()
        if hasattr(self.file, 'getvalue'):
            fileInput.write(self.file.getvalue())
        elif hasattr(self.file, 'read'):
            fileInput.write(self.file.read())
        else:
            raise ValueError("not sure what to do")
        fileInput.seek(0)
        fileOutput = tempfile.NamedTemporaryFile()  # keep this open for the next block

        _fname_input = fileInput.name
        _fname_output = fileOutput.name

        # we need this for filesavings
        filesize_original = utils.file_size(fileInput)

        # run the autodetect
        if not _OPTIMIZE_SUPPORT_DETECTED:
            autodetect_support()

        _optimized = False
        optimizations = []
        if self.format_standardized == 'jpg':
        
            if OPTIMIZE_SUPPORT['jpegtran']['available'] and OPTIMIZE_SUPPORT['jpegtran']['use']:
                _binary = OPTIMIZE_SUPPORT['jpegtran']['binary'] or 'jpegtran'
                _progressive = '-progressive' if OPTIMIZE_SUPPORT['jpegtran']['options']['progressive'] else ''
                r = envoy.run("""%s -copy all -optimize %s -outfile %s %s""" % (_binary, _progressive, _fname_output, _fname_input))
                if r.status_code != 127:
                    _optimized = True
                    optimizations.append(('jpegtran', True))
                else:
                    optimizations.append(('jpegtran', False))

            if OPTIMIZE_SUPPORT['jpegoptim']['available'] and OPTIMIZE_SUPPORT['jpegoptim']['use']:
                print("optimizing with jpegoptim")
                _binary = OPTIMIZE_SUPPORT['jpegoptim']['binary'] or 'jpegoptim'
                r = envoy.run("""%s --strip-all -q %s""" % (_binary, _fname_output, ))
                if r.status_code != 127:
                    _optimized = True
                    optimizations.append(('jpegoptim', True))
                else:
                    optimizations.append(('jpegoptim', False))

        elif self.format_standardized == 'gif':

            if OPTIMIZE_SUPPORT['gifsicle']['available'] and OPTIMIZE_SUPPORT['gifsicle']['use']:
                _binary = OPTIMIZE_SUPPORT['gifsicle']['binary'] or 'gifsicle'
                _gifsicle_level = OPTIMIZE_SUPPORT['gifsicle']['options']['level']
                r = envoy.run("""%s -O%d %s --output %s""" % (_binary, _gifsicle_level, _fname_input, _fname_output))
                if r.status_code != 127:
                    _optimized = True
                    optimizations.append(('gifsicle', True))
                else:
                    optimizations.append(('gifsicle', False))

        elif self.format_standardized == 'png':

            if OPTIMIZE_SUPPORT['pngcrush']['available'] and OPTIMIZE_SUPPORT['pngcrush']['use']:
                _binary = OPTIMIZE_SUPPORT['pngcrush']['binary'] or 'pngcrush'
                # envoy.run("""pngcrush -rem alla -reduce -brute -q %s %s""" % (_fname_input, _fname_output))
                # envoy.run("""pngcrush -rem alla -reduce -q %s %s""" % (_fname_input, _fname_output))
                r = envoy.run("""%s -rem alla -nofilecheck -bail -blacken -reduce -cc %s %s""" % (_binary, _fname_input, _fname_output))
                if r.status_code != 127:
                    _fname_input = _fname_output
                    _optimized = True
                    optimizations.append(('pngcrush', True))
                else:
                    optimizations.append(('pngcrush', False))

            if OPTIMIZE_SUPPORT['optipng']['available'] and OPTIMIZE_SUPPORT['optipng']['use']:
                _binary = OPTIMIZE_SUPPORT['optipng']['binary'] or 'optipng'
                _optipng_level = OPTIMIZE_SUPPORT['optipng']['options']['level']
                # note that we do `--out OUTPUT --(stop) INPUT
                r = envoy.run("""%s -i0 -o%d -out %s -- %s""" % (_binary, _optipng_level, _fname_output, _fname_input))
                if r.status_code != 127:
                    _fname_input = _fname_output
                    _optimized = True
                    optimizations.append(('optipng', True))
                else:
                    optimizations.append(('optipng', False))

            if OPTIMIZE_SUPPORT['advpng']['available'] and OPTIMIZE_SUPPORT['advpng']['use']:
                _binary = OPTIMIZE_SUPPORT['advpng']['binary'] or 'advpng'
                _advpng_level = OPTIMIZE_SUPPORT['advpng']['options']['level']
                # note that we do `--out OUTPUT --(stop) INPUT
                r = envoy.run("""%s -%d -z %s""" % (_binary, _advpng_level, _fname_output))
                if r.status_code != 127:
                    _fname_input = _fname_output
                    _optimized = True
                    optimizations.append(('advpng', True))
                else:
                    optimizations.append(('advpng', False))

        # stash this onto the object
        self.optimizations = optimizations

        if not _optimized:
            self.file.seek(0)
            self.is_optimized = False  # nothing to optimize
            log.debug("optimization_savings = 0 - NO OPTIMIZATIONS POSSIBLE")
            self.optimization_savings = 0

        else:
            fileOutput.seek(0)
            newFile = FilelikePreference()
            newFile.write(fileOutput.read())
            newFile.seek(0)
            self.file = newFile
            self.is_optimized = True

            # so how much did we save?
            filesize_optimized = utils.file_size(newFile)
            optimization_savings = filesize_original - filesize_optimized

            log.debug("optimization_savings = %s" % optimization_savings)
            self.optimization_savings = optimization_savings
        
        # done with these, so close
        fileInput.close()
        fileOutput.close()


class ResizedImage(BasicImage):
    """A class for a ResizedImage Result.
    """

    def __repr__(self):
        return "<ReizedImage at %s - %s >" % (id(self), self.__dict__)


class FakedOriginal(BasicImage):
    """sometimes we need to fake an original file"""
    format = None
    mode = None
    width = None
    height = None
    file_size = None
    file_md5 = None

    def __init__(self, original_filename):
        file_ext = original_filename.split('.')[-1].lower()
        self.format = utils.standardized_to_PIL_type(file_ext)


class ImageWrapper(object):
    """Our base class for image operations"""

    basicImage = None
    pilObject = None

    def get_original(self):
        return self.basicImage

    def __del__(self):
        if self.pilObject is not None:
            self.pilObject.close()

    def __init__(self, imagefile=None, imagefile_name=None, FilelikePreference=None, ):
        """
        registers and validates the image file
        note that we do copy the image file

        args:

        `imagefile`
                cgi.FieldStorage
                _io._CoreFileType = file  # Python2 Only
                _io._CoreFileType = io.IOBase  # Python3 Only
                _io.StringIO.StringIO  # StringIO.StringIO Py3=io.StringIO
                    _io.cStringIO.InputType  # Python2 Only
                    _io.cStringIO.OutputType # Python2 Only
                tempfile.TemporaryFile, tempfile.SpooledTemporaryFile

        `imagefile_name`
            only used for informational purposes

        `FilelikePreference`
            preference class for filelike objects
                _io.cStringIo  # Python2 Only
                _io.StringIO  # Py2=StringIO.StringIO Py3=io.StringIO
                tempfile.SpooledTemporaryFile
        """
        if imagefile is None:
            raise errors.ImageError_MissingFile(utils.ImageErrorCodes.MISSING_FILE)

        if not isinstance(imagefile, _valid_types):
            raise errors.ImageError_Parsing(utils.ImageErrorCodes.UNSUPPORTED_IMAGE_CLASS)

        try:
            # try to cache this all
            file_data = None
            file_name = None
            if isinstance(imagefile, cgi.FieldStorage):
                if not hasattr(imagefile, 'filename'):
                    raise errors.ImageError_Parsing(utils.ImageErrorCodes.MISSING_FILENAME_METHOD)
                imagefile.file.seek(0)
                file_data = imagefile.file.read()

                file_name = ''
                if hasattr(imagefile.file, 'name'):
                    file_name = imagefile.file.name
                elif hasattr(imagefile, 'filename'):
                    file_name = imagefile.filename

                # be kind, rewind; the input obj we no longer care about
                # but someone else might care
                imagefile.file.seek(0)

            elif isinstance(imagefile, _valid_types_nameless):
                imagefile.seek(0)
                file_data = imagefile.read()
                file_name = imagefile_name or ''

                # be kind, rewind; the input obj we no longer care about
                # but someone else might care
                imagefile.seek(0)

            elif isinstance(imagefile, _io._CoreFileType):
                # catch this last
                imagefile.seek(0)
                file_data = imagefile.read()
                # default
                file_name = imagefile_name
                if hasattr(imagefile, 'name'):  # Py3 object may not have this
                    file_name = imagefile.name
                if file_name == '<fdopen>':
                    file_name = imagefile_name or ''

                # be kind, rewind; the input obj we no longer care about
                # but someone else might care
                imagefile.seek(0)

            else:
                # just be safe with an extra else
                raise ValueError("where do i go? ")
                raise errors.ImageError_Parsing(utils.ImageErrorCodes.UNSUPPORTED_IMAGE_CLASS)

            if FilelikePreference is None:
                if _io.cStringIO:
                    FilelikePreference = _io.cStringIO.StringIO
                else:
                    FilelikePreference = _io._FallbackFileType

            # create a new image
            # and stash our data!
            fh_imageData = FilelikePreference()
            fh_imageData.write(file_data)
            fh_imageData.seek(0)
            fh_name = imagefile_name or file_name

            # make the new wrapped obj and then...
            # safety first! just ensure this loads.
            pilObject = Image.open(fh_imageData)
            pilObject.load()
            if not pilObject:
                raise errors.ImageError_Parsing(utils.ImageErrorCodes.INVALID_REBUILD)
            self.pilObject = pilObject

            # finally, stash our data
            wrappedImage = BasicImage(
                fh_imageData,
                name = fh_name,
                format = self.pilObject.format,
                mode = self.pilObject.mode,
                width = self.pilObject.size[0],
                height = self.pilObject.size[1],
                is_image_animated = utils.is_image_animated(self.pilObject),
                animated_image_totalframes = utils.animated_image_totalframes(self.pilObject),
            )
            self.basicImage = wrappedImage

        except IOError:
            raise
            raise errors.ImageError_Parsing(utils.ImageErrorCodes.INVALID_FILETYPE)

        except errors.ImageError as e:
            raise

        except Exception as e:
            raise

    def resize(self, instructions_dict, FilelikePreference=None, ):
        """this does the heavy lifting

        be warned - this uses a bit of memory!

        1. we operate on a copy of the pilObject via _io.cStringIo
            (which is already a copy of the original)
        2. we save to another new _io.cStringIO 'file'

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

            `FilelikePreference` - default preference for file-like objects
        """

        if FilelikePreference is None:
            if _io.cStringIO:
                FilelikePreference = _io.cStringIO.StringIO
            else:
                FilelikePreference = _io._FallbackFileType

        # we analyze the pilObject, because `copy()` only works on the frame
        if utils.is_image_animated(self.pilObject):
            allow_animated = False
            if 'allow_animated' in instructions_dict:
                allow_animated = instructions_dict['allow_animated']
            if not allow_animated:
                raise ValueError("Image is Animated!")

        resized_image = self.pilObject.copy()

        if resized_image.palette:
            resized_image = resized_image.convert()

        constraint_method = 'fit-within'
        if 'constraint-method' in instructions_dict:
            constraint_method = instructions_dict['constraint-method']

        if constraint_method != 'passthrough:no-resize':

            # t_ = target
            # i_ = image / real

            (i_w, i_h) = self.pilObject.size

            t_w = instructions_dict['width']
            t_h = instructions_dict['height']

            crop = ()

            # notice that we only scale DOWN (ie: check that t_x < i_x

            if constraint_method in ('fit-within', 'fit-within:crop-to'):

                # figure out the proportions
                proportion_w = 1
                proportion_h = 1
                if t_w < i_w:
                    proportion_w = t_w / i_w
                if t_h < i_h:
                    proportion_h = t_h / i_h

                if constraint_method == 'fit-within':
                    # peg to the SMALLEST proportion so the entire image fits
                    if proportion_w < proportion_h:
                        proportion_h = proportion_w
                    elif proportion_h < proportion_w:
                        proportion_w = proportion_h
                    # figure out the resizes!
                    t_w = int(i_w * proportion_w)
                    t_h = int(i_h * proportion_h)

                elif constraint_method == 'fit-within:crop-to':
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

            elif constraint_method == 'fit-within:ensure-width':
                proportion = 1
                if t_w < i_w:
                    proportion = t_w / i_w
                t_h = int(i_h * proportion)

            elif constraint_method == 'fit-within:ensure-height':
                proportion = 1
                if t_h < i_h:
                    proportion = t_h / i_h
                t_w = int(i_w * proportion)

            elif constraint_method == 'smallest:ensure-minimum':
                # useful for things like og:image where you want at least a 200px image

                # figure out the proportions
                proportion_w = t_w / i_w
                proportion_h = t_h / i_h

                # we don't want to scale up...
                if (proportion_h > 1 or proportion_w > 1):
                    proportion_h = 1
                    proportion_w = 1

                use_scale = 'h'
                scale_factor = proportion_h
                if proportion_w > proportion_h:
                    use_scale = 'w'
                    scale_factor = proportion_w

                t_h = int(i_h * scale_factor)
                t_w = int(i_w * scale_factor)

            elif constraint_method == 'exact:proportion':
                proportion_w = 1
                proportion_h = 1
                if t_w < i_w:
                    proportion_w = t_w / i_w
                if t_h < i_h:
                    proportion_h = t_h / i_h
                if (proportion_w != proportion_h):
                    raise errors.ImageError_ResizeError('item can not be scaled to exact size')

            elif constraint_method == 'exact:no-resize':
                if (t_w != i_w) or (t_h != i_h):
                    raise errors.ImageError_ResizeError('item is not exact size')

            else:
                raise errors.ImageError_ResizeError('Invalid constraint-method for size recipe: "%s"' % constraint_method)

            if (i_w != t_w) or (i_h != t_h):
                if USE_THUMBNAIL:
                    # the thumbnail is faster, but has been looking uglier in recent versions
                    resized_image.thumbnail([t_w, t_h], Image.ANTIALIAS)
                else:
                    resized_image = resized_image.resize((t_w, t_h, ), Image.ANTIALIAS)

            if len(crop):
                resized_image = resized_image.crop(crop)
                resized_image.load()

        format = 'JPEG'
        if 'format' in instructions_dict:
            format = instructions_dict['format']

        # returns uppercase
        format = utils.derive_output_format(format, self.get_original().format)

        def _get_pil_options(_format):
            pil_options = {}
            if format in ('JPEG', 'PDF', ):
                for i in ('quality', 'optimize', 'progressive'):
                    k = 'save_%s' % i
                    if k in instructions_dict:
                        pil_options[i] = instructions_dict[k]
            elif format == 'PNG':
                for i in ('optimize', 'transparency', 'bits', 'dictionary'):
                    k = 'save_%s' % i
                    if k in instructions_dict:
                        pil_options[i] = instructions_dict[k]
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
            height=resized_image.size[1]
        )
