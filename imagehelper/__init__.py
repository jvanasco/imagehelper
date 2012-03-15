"""
A fork of FindMeOn's image helper routines

code offered via BSD license

supported formats ?:
    GIF
    JPEG
    PNG
    PDF
"""
from __future__ import division

import logging
log = logging.getLogger(__name__)


try:
    import boto
except:
    boto = None

import cStringIO
import Image
import exceptions


_PIL_type_to_content_type= {
    'gif': 'image/gif',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'pdf':'application/pdf',
    'png': 'image/png',
}
def PIL_type_to_content_type( type ):
    if type.lower() in _PIL_type_to_content_type:
        return _PIL_type_to_content_type[type.lower()]
    raise ValueError('invalid type')

_PIL_type_to_standardized= {
    'gif': 'gif',
    'jpg': 'jpg',
    'jpeg': 'jpg',
    'pdf': 'pdf',
    'png': 'png',
}
def PIL_type_to_standardized( type ):
    if type.lower() in _PIL_type_to_standardized:
        return _PIL_type_to_standardized[type.lower()]
    raise ValueError('invalid type')



## offer a handful of errors to trap exceptions


class PhotoError(Exception):
    """Base class for Exceptions"""
    pass

class PhotoError_Parsing(PhotoError):
    pass

class PhotoError_MissingFile(PhotoError):
    pass

class PhotoError_ConfigError(PhotoError):
    pass

class PhotoError_ResizeError(PhotoError):
    pass

class PhotoError_S3Upload(PhotoError):
    pass
    
 
# s3config stores our credentials
class S3Config(object):
    """Configuration info for amazon s3 services"""
    key_public= None
    key_private= None
    bucket_public_name= None
    bucket_archive_name= None
    bucket_public_headers= None
    bucket_archive_headers= None
    
    
    def __init__( self, key_public=None , key_private=None , bucket_public_name=None , bucket_archive_name=None , bucket_public_headers=None , bucket_archive_headers=None ):
        self.key_public= key_public
        self.key_private= key_private
        self.bucket_public_name= bucket_public_name
        self.bucket_archive_name= bucket_archive_name
        self.bucket_public_headers= bucket_public_headers
        self.bucket_archive_headers= bucket_archive_headers
    

class S3Logger(object):
    """The s3 save method will log to this logger on uploads and deletes.  Any object offering these methods can be replaced; this is only illustrative."""
    def log_upload( self, bucket=None, key=None ):
        pass

    def log_delete( self, bucket=None, key=None ):
        pass


## offer a config for resizing items
class ResizerConfig(object):
    """ResizerFactory allows you to specify what/how to resize.
    
        You could subclass this configuator - just instantiate the object with is_subclass=True to preserve your vars, or configure one on the fly with __init__()

        `photo_resizes` - a dict in this format:
            {   'size_name' : {
					'width': 120,
					'height': 120,
					'constraint-method': 'fit-within',
					'save_quality': 50,
					'filename_template': '%(guid)s.%(format)s',
					'suffix': 't1',
					'format':'JPEG',
					's3_bucket_public': 'my-test',
					's3_headers': { 'x-amz-acl' : 'public-read' }
                }
            }
            
        `photo_resizes_selected` : an array of size names ( see above ) to be resized
        
        width*
        	in pixels
        height*
        	in pixels
        format
        	defaults to JPEG
        constraint-method
        	see below for valid constraint methods
        save_
	        keys prepended with `save_` are stripped of "save" and passed on to PIL.  
	        warning: different formats accept different arguments. view the code in 'resize' to see what works.
	    filename_template 
	     	defaults to "%(guid)s-%(suffix)s.%(format)s"
	     	pass in any python string template you desire -- guid, suffix and format are interpolated. 
	    suffix
	    	give the size a custom suffix (for filename_template)
	    	otherwise this defaults to the 'size_name'
	    s3_bucket_public
	    	overwrite the bucket that resized items are saved to ( defaults to config object settings )
	    s3_headers
	    	overwrite the aws headers this is saved with ( defaults to '{ 'x-amz-acl' : 'public-read' }' + config object settings )
	    	
	    
        valid constraint methods:
        
            fit-within
                Resizes item to fit within the bounding box , on both height and width. 
                This resulting image will be the size of the bounding box or smaller.

            fit-within:crop-to
                resizes the item along whichever axis ensures the bounding box is 100% full, then crops. 
                This resulting image will be the size of the bounding box.
                
            fit-within:ensure-width
                resizes item to fit within the bounding box, scaling height to ensure 100% width
                This resulting image will be the size of the bounding box.

            fit-within:ensure-height
                resizes item to fit within the bounding box, scaling width to ensure 100% height
                This resulting image will be the size of the bounding box.

            exact
                tries to scale the image to an exact size.  raises an error if it can't.
                usually this is used to resample a 1:1 image, however this might be used to drop an image to a specific proportion.
        
    """
    photo_resizes= None
    photo_resizes_selected= None
    
    def __init__( self , photo_resizes=None , photo_resizes_selected=None , s3_config=None , is_subclass=False ):
        if not is_subclass:
            self.photo_resizes= photo_resizes
            self.photo_resizes_selected= photo_resizes_selected


class ResizerFactory(object):
    """This is a conveniece Factory to store application configuration options."""
    resizer_config= None
    s3_config= None
    
    def __init__( self , resizer_config=resizer_config , s3_config=s3_config ):
        self.resizer_config = resizer_config
        self.s3_config = s3_config
        
    def resize( self , photofile=None , guid=None, s3_save=False , s3_save_original=True , s3_logger=None ):
        """Creates a wrapped object, performs resizing /saving on it, then returns it"""
        wrapped= ResizerWrapper( resizer_config=self.resizer_config , s3_config=self.s3_config)
        wrapped.register_image_file( photofile=photofile )
        wrapped.resize()
        if s3_save:
            results= wrapped.s3_save( guid=guid, s3_save_original=s3_save_original , s3_logger=s3_logger )
        return wrapped

        
    

class ResizerWrapper(object):
    """This is a wrapped item.  It stores a photo file, it's metadata, and the various resizes.  it's the workhorse."""
    imageFileObject = None
    imageObject = None
    imageObject_width= None
    imageObject_height= None
    imageObject_name = None
    
    resizer_config= None
    s3_config= None
    s3_saved= None

    resized= None
    
    
    def __init__( self , resizer_config=None , s3_config=None ):
        self.resizer_config = resizer_config
        self.s3_config = s3_config
        self.resized= {}
        self.s3_saved = {}
        
        
    


    def register_image_file( self,  photofile=None ):
        """registers an image file """
        
        # register & validate the file

        if photofile is None:
            raise PhotoError_MissingFile('No photofile')
        if photofile.__class__.__name__ != 'FieldStorage' and photofile.__class__.__name__ != 'file':
            raise PhotoError_Parsing('Must be cgi.FieldStorage or file')

        try:
            # try to cache this all
            data= None
            if photofile.__class__.__name__ == 'FieldStorage':
                if not hasattr( photofile , 'filename' ):
                    raise PhotoError_MissingFile("photofile does not hasattr 'filename'")
                photofile.file.seek(0)
                data= photofile.file.read()
                imageObject_name= photofile.file.name
            elif photofile.__class__.__name__ == 'file':
                photofile.seek(0)
                data= photofile.read()
                imageObject_name= photofile.name
            imageFileObject= cStringIO.StringIO()
            imageFileObject.write(data)
            imageFileObject.seek(0)
            imageObject= Image.open(imageFileObject)
            imageObject.load()
        except exceptions.IOError:
            raise PhotoError_Parsing('INVALID_FILETYPE')
        except :
            raise PhotoError_Parsing('INVALID_OTHER')
        if not imageObject:
            raise PhotoError_Parsing('NO_IMAGE')
        self.imageFileObject = imageFileObject
        self.imageObject = imageObject
        self.imageObject_name= imageObject_name
        ( self.imageObject_width , self.imageObject_height ) = self.imageObject.size


    def resize( self , photofile=None , photo_resizes=None , photo_resizes_selected=None ):
        """
            Returns a dict of resized photos
            calls self.register_image_file() if needed
            
            this resizes the images. 
            it returns the images and updates the internal dict.
        """
        if photo_resizes is None:
            photo_resizes= self.resizer_config.photo_resizes
        if photo_resizes_selected is None:
            photo_resizes_selected= self.resizer_config.photo_resizes_selected
            
        if not len(photo_resizes.keys()):
            raise PhotoError_ConfigError("We have no photo_resizes...  error")
        if not len(photo_resizes_selected):
            raise PhotoError_ConfigError("We have no photo_resizes_selected...  error")

        if photofile :
            self.register_image_file(photofile=photofile)
        else:
            if not self.imageFileObject :
               raise PhotoError_ConfigError("Please pass in a `photofile` if you have not set an imageFileObject yet")
            
        # we'll stash the items here
        resized= {}
        for size in photo_resizes_selected:
            resized_image= self.imageObject.copy()
            if resized_image.palette:
                resized_image= resized_image.convert()
                
            constraint_method= 'fit-within'
            if 'constraint-method' in photo_resizes[ size ]:
                constraint_method= photo_resizes[ size ]['constraint-method']

            # t_ = target
            # i_ = image / real

            ( i_w , i_h )= ( self.imageObject_width , self.imageObject_height )

            t_w= photo_resizes[ size ]['width']
            t_h= photo_resizes[ size ]['height']
            
            crop= []

            # notice that we only scale DOWN ( ie: check that t_x < i_x

            if constraint_method == 'fit-within' or constraint_method == 'fit-within:crop-to' :

                # figure out the proportions
                proportion_w = 1
                proportion_h = 1
                if t_w < i_w :
                    proportion_w= t_w / i_w 
                if t_h < i_h :
                    proportion_h= t_h / i_h 
                    
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
                    crop_w= t_w
                    crop_h= t_h
                
                    # figure out the resizes!
                    t_w = int ( i_w * proportion_w )
                    t_h = int ( i_h * proportion_h )
                    
                    if ( crop_w != t_w ) or ( crop_h != t_h ):
                    
                        # support_hack_against_artifacting handles an issue where .thumbnail makes stuff look like shit
                        # except we're not using .thumbnail anymore; we're using resize directly
                        support_hack_against_artifacting= False
                        if support_hack_against_artifacting:
                            if t_w < i_w:
                                t_w+= 1
                            if t_h < i_h:
                                t_h+= 1
                    
                        ( x0, y0 , x1 , y1 )= ( 0 , 0 , t_w , t_h )
                        
                        if t_w > crop_w :
                            x0= int( ( t_w / 2 ) - ( crop_w / 2 ) )
                            x1= x0 + crop_w
                
                        if t_h > crop_h :
                            y0= int( ( t_h / 2 ) - ( crop_h / 2 ) )
                            y1= y0 + crop_h
                            
                        crop= ( x0 , y0 , x1 , y1 ) 

            else:
            
                if constraint_method == 'fit-within:ensure-width':
                    proportion= 1
                    if t_w < i_w :
                        proportion= t_w / i_w 
                    t_h = int ( i_h * proportion )

                elif constraint_method == 'fit-within:ensure-height':
                    proportion= 1
                    if t_h < i_h :
                        proportion= t_h / i_h 
                    t_w = int ( i_w * proportion )

                elif constraint_method == 'exact':
                    proportion_w = 1
                    proportion_h = 1
                    if t_w < i_w :
                        proportion_w= t_w / i_w 
                    if t_h < i_h :
                        proportion_h= t_h / i_h 
                    if ( proportion_w != proportion_h ) :
                        raise PhotoError_ResizeError( 'item can not be scaled to exact size' )

                else:
                    raise PhotoError_ResizeError( 'Invalid constraint-method for size: %s' % size )


            if ( i_w != t_w ) or ( i_h != t_h ) :
                #resized_image.thumbnail(  [ t_w , t_h ] , Image.ANTIALIAS )
                resized_image= resized_image.resize([ t_w , t_h ],Image.ANTIALIAS)
                
            if len(crop):
                resized_image= resized_image.crop(crop)
                resized_image.load()
            
            format= 'JPEG'
            if 'format' in photo_resizes[ size ]:
                format= photo_resizes[ size ]['format'].upper()
                
            pil_options= {}
            if format == 'JPEG' or format == 'PDF':
                if 'save_quality' in photo_resizes[ size ]:
                    pil_options['quality'] = photo_resizes[ size ]['save_quality']
                if 'save_optimize' in photo_resizes[ size ]:
                    pil_options['optimize'] = photo_resizes[ size ]['save_optimize']
                if 'save_progressive' in photo_resizes[ size ]:
                    pil_options['progressive'] = photo_resizes[ size ]['save_progressive']
            elif format == 'PNG':
                if 'save_optimize' in photo_resizes[ size ]:
                    pil_options['optimize'] = photo_resizes[ size ]['save_optimize']
                if 'save_transparency' in photo_resizes[ size ]:
                    pil_options['transparency'] = photo_resizes[ size ]['save_transparency']
                if 'save_bits' in photo_resizes[ size ]:
                    pil_options['bits'] = photo_resizes[ size ]['save_bits']
                if 'save_dictionary' in photo_resizes[ size ]:
                    pil_options['dictionary'] = photo_resizes[ size ]['save_dictionary']
            resized_file= cStringIO.StringIO()
            resized_image.save( resized_file, format , **pil_options )
            resized[ size ]= { 'image': resized_image , 'file': resized_file , 'format': format }
        
        for k in resized.keys():
            self.resized[k] = resized[k]
        
        return resized
        

    def s3_save( self , resized=None , photo_resizes=None , guid=None, photo_resizes_selected=None , s3_config=None ,  s3_save_original=False , s3_logger=None ):
        """
            Returns a dict of resized photos
            calls self.register_image_file() if needed
            
            this resizes the images. 
            it returns the images and updates the internal dict.
        """
        if guid is None:
            raise PhotoError_ConfigError("You must supply a `guid` for the image")
        if resized is None:
            resized= self.resized
        if photo_resizes is None:
            photo_resizes= self.resizer_config.photo_resizes
        if photo_resizes_selected is None:
            photo_resizes_selected= self.resizer_config.photo_resizes_selected
            
        for k in photo_resizes_selected:
           if k not in resized :
                raise PhotoError_ConfigError("selected size is not resized")
           if k not in photo_resizes :
                raise PhotoError_ConfigError("selected size is not photo_resizes")
        
        if boto is None:
            raise ValueError("""boto is not installed""")
    
        if s3_config is None:
           s3_config= self.s3_config

        # public and archive get diff. acls / content-types
        s3headers_public_default= { 'x-amz-acl' : 'public-read' }
        if s3_config.bucket_public_headers:
            for k in s3_config.bucket_public_headers:
                s3headers_public_default[k]= s3_config.bucket_public_headers[k]
        s3headers_archive_default= {}
        if s3_config.bucket_archive_headers:
            for k in s3_config.bucket_archive_headers:
                s3headers_archive_default[k]= s3_config.bucket_archive_headers[k]
        
        # setup the s3 connection
        s3_connection = boto.connect_s3( s3_config.key_public , s3_config.key_private )
        s3_buckets= {}
        s3_buckets['@public'] = boto.s3.bucket.Bucket( connection=s3_connection , name=s3_config.bucket_public_name )
        if s3_save_original :
            s3_buckets['@archive'] = boto.s3.bucket.Bucket( connection=s3_connection , name=s3_config.bucket_archive_name )
            
        for size in photo_resizes_selected:
            if 's3_bucket_public' in photo_resizes[size]:
                bucket_name= photo_resizes[size]['s3_bucket_public']
                s3_buckets[bucket_name] = boto.s3.bucket.Bucket( connection=s3_connection , name=bucket_name )

        # log uploads for removal/tracking and return           
        s3_uploads= {}
        try:
            # and then we upload...
            for size in photo_resizes_selected:
                filename_template= "%(guid)s-%(suffix)s.%(format)s"
                if 'filename_template' in photo_resizes[size]:
                    filename_template= photo_resizes[size]['filename_template']
                if 'suffix' in photo_resizes[ size ]:
                    suffix= photo_resizes[ size ]['suffix']
                else:
                    suffix= size
                target_filename=  filename_template % {\
                        'guid': guid , 
                        'suffix': suffix , 
                        'format': PIL_type_to_standardized( resized[size]['format']) 
                    }
                if 's3_bucket_public' in photo_resizes[size] :
                    bucket_name = photo_resizes[size]['s3_bucket_public']
                    bucket= s3_buckets[ bucket_name ]
                else:
                    bucket_name = s3_config.bucket_public_name
                    bucket= s3_buckets['@public']
                log.debug("Uploading %s to %s " % ( target_filename , bucket ))
                _s3_headers= s3headers_public_default.copy()
                _s3_headers['Content-Type'] = PIL_type_to_content_type( resized[size]['format'] )
                if 's3_headers' in photo_resizes[size]:
                    for k in photo_resizes[size]['s3_headers']:
                        _s3_headers[k]= photo_resizes[size]['s3_headers'][k]
                s3_key= boto.s3.key.Key( bucket )
                s3_key.key= target_filename
                s3_key.set_contents_from_string( resized[size]['file'].getvalue() , headers=_s3_headers )
                # log for removal/tracking & return
                if bucket_name not in s3_uploads:
                    s3_uploads[bucket_name]= {}
                s3_uploads[bucket_name][size]= target_filename
                if s3_logger:
                    s3_logger.log_upload( bucket=bucket_name , key=target_filename )
            if s3_save_original :
                bucket_name= s3_config.bucket_archive_name
                bucket= s3_buckets['@archive']
                original_image_suffix= PIL_type_to_standardized( self.imageObject.format )
                _s3_headers= s3headers_archive_default.copy()
                _s3_headers['Content-Type'] = PIL_type_to_content_type( self.imageObject.format )
                # no need to set acl, its going to be owner-only by default
                target_filename= "%s.%s" % ( guid , original_image_suffix )
                log.debug("Uploading %s to %s " % ( target_filename , bucket_name ))
                s3_key_original= boto.s3.key.Key( bucket )
                s3_key_original.key= target_filename
                s3_key_original.set_contents_from_string( self.imageFileObject.getvalue() , headers=_s3_headers )
                # log for removal/tracking & return
                if bucket_name not in s3_uploads:
                    s3_uploads[bucket_name]= {}
                s3_uploads[bucket_name][size]= target_filename
                if s3_logger:
                    s3_logger.log_upload( bucket=bucket_name , key=target_filename )
        except:
            # if we have ANY issues, we want to delete everything from amazon s3. otherwise this stuff is just hiding up there
            log.debug("Error uploading... rolling back s3 items")
            for bucket_name in s3_uploads:
                if bucket_name == s3_config.bucket_public_name:
                    bucket= s3_buckets['@archive']
                elif bucket_name == s3_config.bucket_archive_name:
                    bucket= s3_buckets['@public']
                else:
                    bucket= s3_buckets[bucket_name]
                for size in s3_uploads[bucket_name]:
                    target_filename= s3_uploads[bucket_name][size]
                    removal= boto.s3.key.Key( bucket )
                    removal.key= target_filename
                    removal.delete()
                    if s3_logger:
                        s3_logger.log_delete( bucket=bucket_name , key=target_filename )
                    del s3_uploads[bucket_name][size]
                del s3_uploads[bucket_name]
            raise PhotoError_S3Upload('error uploading')
        for bucket_name in s3_uploads:
            if bucket_name not in self.s3_saved :
               self.s3_saved[bucket_name]= {}
            for size in s3_uploads[bucket_name]:
               self.s3_saved[bucket_name][size]= s3_uploads[bucket_name][size]
        return s3_uploads
    
        