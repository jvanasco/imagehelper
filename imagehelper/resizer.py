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

        `resizesSchema` - a dict in this format:
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
            
        `selected_resizes` : an array of size names ( see above ) t
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
        
            see `imagehelper.image_wrapper.ImageWrapper().resize()` for full
            details
            
            'exact:no-resize'
            'exact:proportion'
            'fit-within'
            'fit-within:crop-to'
            'fit-within:ensure-height'
            'fit-within:ensure-width'
            'smallest:ensure-minimum'
            

    """
    resizesSchema = None
    selected_resizes= None
    
    def __init__( self , resizesSchema=None , selected_resizes=None , 
            is_subclass=False ,
        ):
        if not is_subclass:
            self.resizesSchema = resizesSchema
            if selected_resizes is None :
                self.selected_resizes = resizesSchema.keys()
            else:
                self.selected_resizes = selected_resizes


class ResizerFactory(object):
    """This is a conveniece Factory to store application configuration 
    options.
    
    You can create a single ResizerFactory in your application, then
    just use it to continually resize images.  Factories have no state, they
    simply hold configuration information, so they're threadsafe.    
    """
    resizerConfig= None
    

    def __init__( self , resizerConfig=None ):
        """
        args
            `resizerConfig`
                a resizer.ResizerConfig instance
        """
        self.resizerConfig = resizerConfig
        

    def resize( self , imagefile=None ):
        """Creates a wrapped object, performs resizing /saving on it, 
        then returns it
        
        note that this returns a `ResizerResultset` object

        args
            `imagefile`
                an object supported by image_wrapper
                usually:
                    file
                    cgi.fi

        """
        resizer = Resizer( resizerConfig=self.resizerConfig )
        resizer.register_image_file( imagefile=imagefile )
        resizedImages = resizer.resize()
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
    resizerConfig = None
    resizerResultset = None
    imageWrapper = None
    
    def __init__( self , resizerConfig=None ):
        self.resizerConfig = resizerConfig
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


    def resize( self , imagefile=None , resizesSchema=None , selected_resizes=None ):
        """
            Returns a dict of resized images
            calls self.register_image_file() if needed
            
            this resizes the images. 
            it returns the images and updates the internal dict.
            
            the internal dict will have an @archive object as well
        """
        if resizesSchema is None:
            if self.resizerConfig :
                resizesSchema = self.resizerConfig.resizesSchema
            else:
                raise ValueError("no resizesSchema and no self.resizerConfig")

        if selected_resizes is None:
            if self.resizerConfig :
                selected_resizes = self.resizerConfig.selected_resizes
            else:
                raise ValueError("no selected_resizes and no self.resizerConfig")
            
        if not len(resizesSchema.keys()):
            raise errors.ImageError_ConfigError("We have no resizesSchema...  error")

        if not len(selected_resizes):
            raise errors.ImageError_ConfigError("We have no selected_resizes...  error")

        if imagefile :
            self.register_image_file( imagefile=imagefile )
            
        if not self.imageWrapper :
           raise errors.ImageError_ConfigError("Please pass in a `imagefile` if you have not set an imageFileObject yet")
           
        # we'll stash the items here
        resized= {}
        for size in selected_resizes:
            if size[0] == "@":
                raise errors.ImageError_ConfigError("@ is a reserved initial character for image sizes")
                
            ## imageWrapper.resize returns a ResizedImage that has attributes `.resized_image`, `image_format`
            resized[ size ]= self.imageWrapper.resize( resizesSchema[ size ] )
            
        resizerResultset = ResizerResultset(
            resized = resized , 
            original = self.imageWrapper.get_original() ,
        )
        self.resizerResultset = resizerResultset

        return resizerResultset
    
             
