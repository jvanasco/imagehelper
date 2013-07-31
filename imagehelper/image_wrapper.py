from __future__ import division

import logging
log = logging.getLogger(__name__)


try:
    from PIL import Image
except ImportError:
    import Image


import cgi
import cStringIO
import StringIO
import types


from . import errors
from . import utils


USE_THUMBNAIL = False

class ResizedImage(object):
    """A class for a ResizedImage Result.
    
        `file` 
            a cStringIO file representation
        
        `format`
        `name`
        `mode`
        `width`
        `height`
            resized file attributes
        
        `filesize`
            property to calculate the filesize 
        
    """
    def __init__( self , resized_file , format=None , name=None , mode=None , 
            width=None, height=None ,
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
        self.file = resized_file
        self.file.seek(0) # be kind, rewind
        self.name = name
        self.format = format
        self.mode = mode
        self.width = width
        self.height = height
    
    def __repr__(self):
        return "<ReizedImage at %s - %s >" % ( id(self) , self.__dict__ )

    @property
    def filesize(self):
        """property; calculate the filesize"""
        return utils.filesize( self.file )    
    

class ImageWrapper(object):
    """Our base class for image operations"""

    imageFileObject = None
    imageObject = None
    imageObject_name = None
    imageObject_mode = None
    
    
    def __init__(self , imagefile=None , imagefile_name=None ):
        """registers and validates the image file
            note that we do copy the image file
        """
        if imagefile is None:
            raise errors.ImageError_MissingFile( constants.ImageErrorCodes.MISSING_FILE )

        if not isinstance( imagefile , ( cgi.FieldStorage , types.FileType , StringIO.StringIO , cStringIO.InputType, cStringIO.OutputType ) ):
            raise errors.ImageError_Parsing( constants.ImageErrorCodes.UNSUPPORTED_IMAGE_CLASS )

        try:
            # try to cache this all
            data = None
            if isinstance( imagefile , cgi.FieldStorage ):
                if not hasattr( imagefile , 'filename' ):
                    raise errors.ImageError_Parsing( constants.ImageErrorCodes.MISSING_FILENAME_METHOD )
                imagefile.file.seek(0)
                data = imagefile.file.read()
                imageObject_name = imagefile.file.name
            elif isinstance( imagefile , types.FileType ):
                imagefile.seek(0)
                data = imagefile.read()
                imageObject_name = imagefile.name
            elif isinstance( imagefile , (StringIO.StringIO , cStringIO.InputType, cStringIO.OutputType) ):
                imagefile.seek(0)
                data = imagefile.read()
                imageObject_name = imagefile_name or "unknown"

            # be kind, rewind; the input obj we no longer care about
            imagefile.seek(0)

            # create a new image
            imageFileObject = cStringIO.StringIO()
            imageFileObject.write(data)
            imageFileObject.seek(0)

            # make the new wrapped obj and then...
            # safety first! just ensure this loads.
            imageObject = Image.open(imageFileObject)
            imageObject.load()

            if not imageObject:
                raise errors.ImageError_Parsing( constants.ImageErrorCodes.INVALID_REBUILD )

            # great, stash our data!
            self.imageFileObject = imageFileObject
            self.imageObject = imageObject
            self.imageObject_name = imageObject_name
            self.imageObject_mode = self.imageObject.mode

        except IOError:
            raise errors.ImageError_Parsing( constants.ImageErrorCodes.INVALID_FILETYPE )
        
        except errors.ImageError , e:
            raise

        except Exception as e :
            raise


    def resize( self , instructions_dict ):
        """this does the heavy lifting
        
        be warned - this uses a bit of memory!
            
        1. we operate on a copy of the imageObject via cStringIo
            ( which is already a copy of the original )
        2. we save to another new cStringIO 'file'
        
        """

        resized_image = self.imageObject.copy()
        if resized_image.palette:
            resized_image = resized_image.convert()
            
        constraint_method = 'fit-within'
        if 'constraint-method' in instructions_dict:
            constraint_method = instructions_dict['constraint-method']

        # t_ = target
        # i_ = image / real

        ( i_w , i_h ) = self.imageObject.size

        t_w = instructions_dict['width']
        t_h = instructions_dict['height']
        
        crop = ()

        # notice that we only scale DOWN ( ie: check that t_x < i_x

        if constraint_method in ( 'fit-within' , 'fit-within:crop-to' ):

            # figure out the proportions
            proportion_w = 1
            proportion_h = 1
            if t_w < i_w :
                proportion_w = t_w / i_w 
            if t_h < i_h :
                proportion_h = t_h / i_h 
                
            if constraint_method == 'fit-within':
                # peg to the SMALLEST proportion so the entire image fits
                if proportion_w < proportion_h:
                    proportion_h = proportion_w
                elif proportion_h < proportion_w:
                    proportion_w = proportion_h
                # figure out the resizes!
                t_w = int ( i_w * proportion_w )
                t_h = int ( i_h * proportion_h )

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
                t_w = int ( i_w * proportion_w )
                t_h = int ( i_h * proportion_h )
                
                if ( crop_w != t_w ) or ( crop_h != t_h ):
                
                    # support_hack_against_artifacting handles an issue where .thumbnail makes stuff look like shit
                    # except we're not using .thumbnail anymore; we're using resize directly
                    support_hack_against_artifacting = USE_THUMBNAIL
                    if support_hack_against_artifacting:
                        if t_w < i_w:
                            t_w += 1
                        if t_h < i_h:
                            t_h += 1
                
                    ( x0, y0 , x1 , y1 )= ( 0 , 0 , t_w , t_h )
                    
                    if t_w > crop_w :
                        x0 = int( ( t_w / 2 ) - ( crop_w / 2 ) )
                        x1 = x0 + crop_w
            
                    if t_h > crop_h :
                        y0 = int( ( t_h / 2 ) - ( crop_h / 2 ) )
                        y1 = y0 + crop_h
                        
                    crop = ( x0 , y0 , x1 , y1 ) 

        elif constraint_method == 'fit-within:ensure-width':
            proportion = 1
            if t_w < i_w :
                proportion = t_w / i_w 
            t_h = int ( i_h * proportion )

        elif constraint_method == 'fit-within:ensure-height':
            proportion = 1
            if t_h < i_h :
                proportion = t_h / i_h 
            t_w = int ( i_w * proportion )


        elif constraint_method == 'smallest:ensure-minimum':
            ## useful for things like og:image where you want at least a 200px image
        
            # figure out the proportions
            proportion_w = t_w / i_w 
            proportion_h = t_h / i_h 
                
            # we don't want to scale up...
            if ( proportion_h > 1 or proportion_w > 1 ) :
                proportion_h = 1
                proportion_w = 1
                
            use_scale = 'h'
            scale_factor = proportion_h
            if proportion_w > proportion_h :
                use_scale = 'w'
                scale_factor = proportion_w
            
            t_h = int(i_h * scale_factor)
            t_w = int(i_w * scale_factor)


        elif constraint_method == 'exact':
            proportion_w = 1
            proportion_h = 1
            if t_w < i_w :
                proportion_w = t_w / i_w 
            if t_h < i_h :
                proportion_h = t_h / i_h 
            if ( proportion_w != proportion_h ) :
                raise errors.ImageError_ResizeError( 'item can not be scaled to exact size' )

        elif constraint_method == 'exact:no-resize':
            if ( t_w != i_w ) or ( t_h != i_h ) :
                raise errors.ImageError_ResizeError( 'item is not exact size' )

        else:
            raise errors.ImageError_ResizeError( 'Invalid constraint-method for size recipe: "%s"' % constraint_method )


        if ( i_w != t_w ) or ( i_h != t_h ) :
            if USE_THUMBNAIL :
                ## the thumbnail is faster , but has been looking uglier in recent versions
                resized_image.thumbnail(  [ t_w , t_h ] , Image.ANTIALIAS )
            else:
                resized_image = resized_image.resize( ( t_w, t_h, ) , Image.ANTIALIAS )
            
        if len(crop):
            resized_image = resized_image.crop(crop)
            resized_image.load()
        
        format = 'JPEG'
        if 'format' in instructions_dict:
            format = instructions_dict['format'].upper()
            
        pil_options = {}
        if format in ( 'JPEG' , 'PDF' , ) :
            for i in ( 'quality', 'optimize', 'progressive' ):
                k = 'save_%s' % i
                if k in instructions_dict:
                    pil_options[i] = instructions_dict[k]
        elif format == 'PNG':
            for i in ( 'optimize', 'transparency' , 'bits', 'dictionary' ):
                k = 'save_%s' % i
                if k in instructions_dict:
                    pil_options[i] = instructions_dict[k]

        ## save the image !
        resized_image_file = cStringIO.StringIO()
        resized_image.save( resized_image_file , format , **pil_options )

        return ResizedImage( resized_image_file , format=format , 
            width=resized_image.size[0] , height=resized_image.size[1] )

    def get_original( self ):
        return ResizedImage( self.imageFileObject , name=self.imageObject_name , 
            format=self.imageObject.format , mode=self.imageObject.mode , 
            width=self.imageObject.size[0] , height=self.imageObject.size[1] )


