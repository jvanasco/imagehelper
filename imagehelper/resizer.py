import image_wrapper
import errors


try:
    from PIL import Image
except ImportError:
    import Image


class ResizerConfig(object):
    """ResizerFactory allows you to specify what/how to resize.
    
        You could subclass this configuator - just instantiate the object with 
            `is_subclass = True` 
        to preserve your vars, or configure one on the fly with __init__()

        `photo_resizes` - a dict in this format:
            {   'size_name' : {
                    'width': 120,
                    'height': 120,
                    'constraint-method': 'fit-within',
                    'save_quality': 50,
                    'filename_template': '%(guid)s.%(format)s',
                    'suffix': 't1',
                    'format':'JPEG',
                },
                'other_size_name' : {...},
            }
            
        `photo_resizes_selected` : an array of size names ( see above ) t
            o be resized
        
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
        
            fit-within

                Resizes item to fit within the bounding box , on both height 
                and width.   This resulting image will be the size of the 
                bounding box or smaller.

            fit-within:crop-to

                resizes the item along whichever axis ensures the bounding box 
                is 100% full, then crops.  This resulting image will be the 
                size of the bounding box.
                
            fit-within:ensure-width
                resizes item to fit within the bounding box, scaling height 
                to ensure 100% width.  This resulting image will be the size of 
                the bounding box.

            fit-within:ensure-height
                resizes item to fit within the bounding box, scaling width to 
                ensure 100% height. This resulting image will be the size of 
                the bounding box.

            exact
                tries to scale the image to an exact size.  raises an error if 
                it can't.  Usually this is used to resample a 1:1 image, however
                 this might be used to drop an image to a specific proportion.
        
    """
    image_resizes = None
    image_resizes_selected= None
    
    def __init__( self , image_resizes=None , image_resizes_selected=None , 
            is_subclass=False ,
        ):
        if not is_subclass:
            self.image_resizes = image_resizes
            self.image_resizes_selected = image_resizes_selected


class ResizerFactory(object):
    """This is a conveniece Factory to store application configuration 
    options.
    
    You can create a single ResizerFactory in your application, then
    just use it to continually resize images.  Factories have no state, they
    simply hold configuration information, so they're threadsafe.    
    """
    resizer_config= None
    

    def __init__( self , resizer_config=None ):
        self.resizer_config = resizer_config
        

    def resize( self , imagefile=None ):
        """Creates a wrapped object, performs resizing /saving on it, 
        then returns it
        
        note that this returns a `ResizerResultset` object

        """
        wrapped= Resizer( resizer_config=self.resizer_config )
        wrapped.register_image_file( imagefile=imagefile )
        resizedImages = wrapped.resize()
        return resizedImages
        
        
class ResizerResultset(object):
    resized = None
    original = None
    
    def __init__( self , resized , original=None ):
        self.resized = resized
        self.original = original


class Resizer(object):
    """Resizer is our workhorse.
    It stores the image file, the metadata, and the various resizes."""
    resizer_config = None
    resizerResultset = None
    imageWrapper = None
    
    def __init__( self , resizer_config=None ):
        self.resizer_config = resizer_config
        self.reset()
        
    def reset(self):
        """if you resize a second item, you will need to reset"""
        self.resizerResultset = None
        self.imageWrapper = None
        

    def register_image_file( self,  imagefile=None , imageWrapper=None ):
        """registers a file to be resized"""
        
        if self.imageWrapper is not None :
            raise errors.ImageError_DuplicateAction("We already have registered a file.")
    
        if all( ( imagefile , imageWrapper ) ):
            raise errors.ImageError_ConfigError("Submit only imagefile /or/ imageWrapper")

        if not any( ( imagefile , imageWrapper ) ):
            raise errors.ImageError_ConfigError("Must submit either imagefile /or/ imageWrapper")
            
        if imagefile :
            self.imageWrapper = image_wrapper.ImageWrapper( imagefile = imagefile )

        elif imageWrapper:
            if not isinstance( imageWrapper , image_wrapper.ImageWrapper ):
                raise errors.ImageError_ConfigError("imageWrapper must be of type `imaage_wrapper.ImageWrapper`")
            self.imageWrapper = imageWrapper


    def resize( self , imagefile=None , image_resizes=None , image_resizes_selected=None ):
        """
            Returns a dict of resized images
            calls self.register_image_file() if needed
            
            this resizes the images. 
            it returns the images and updates the internal dict.
            
            the internal dict will have an @archive object as well
        """
        if image_resizes is None:
            image_resizes= self.resizer_config.image_resizes

        if image_resizes_selected is None:
            image_resizes_selected= self.resizer_config.image_resizes_selected
            
        if not len(image_resizes.keys()):
            raise errors.ImageError_ConfigError("We have no image_resizes...  error")

        if not len(image_resizes_selected):
            raise errors.ImageError_ConfigError("We have no image_resizes_selected...  error")

        if imagefile :
            self.register_image_file( imagefile=imagefile )
            
        if not self.imageWrapper :
           raise errors.ImageError_ConfigError("Please pass in a `imagefile` if you have not set an imageFileObject yet")
           
        # we'll stash the items here
        resized= {}
        for size in image_resizes_selected:
            if size[0] == "@":
                raise errors.ImageError_ConfigError("@ is a reserved initial character for image sizes")
                
            ## imageWrapper.resize returns a ResizedImage that has attributes `.resized_image`, `image_format`
            resized[ size ]= self.imageWrapper.resize( image_resizes[ size ] )
            
        resizerResultset = ResizerResultset(
            resized = resized , 
            original = self.imageWrapper.get_original() ,
        )
        self.resizerResultset = resizerResultset

        return resizerResultset
    
             
