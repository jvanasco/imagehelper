import logging
log = logging.getLogger(__name__)

logging.basicConfig(filename="boto.log", level=logging.DEBUG)

from . import utils

try:
    import boto
    import boto.s3
    import boto.s3.bucket
except:
    boto = None


class S3Config(object):
    """Configuration info for amazon s3 services"""
    key_public = None
    key_private = None
    bucket_public_name = None
    bucket_archive_name = None
    bucket_public_headers = None
    bucket_archive_headers = None
    archive_original = None
    
    def __init__(\
            self, 
            key_public = None , 
            key_private = None , 
            bucket_public_name = None , 
            bucket_archive_name = None , 
            bucket_public_headers = None , 
            bucket_archive_headers = None ,
            archive_original = None ,
        ):
        self.key_public = key_public
        self.key_private = key_private
        self.bucket_public_name = bucket_public_name
        self.bucket_archive_name = bucket_archive_name
        self.bucket_public_headers = bucket_public_headers
        self.bucket_archive_headers = bucket_archive_headers
        self.archive_original = archive_original


class S3Logger(object):
    """The s3 save method will log to this logger on uploads and deletes.  
    Any object offering these methods can be replaced; 
    This is only illustrative."""

    def log_upload( self, bucket=None, key=None ):
        pass

    def log_delete( self, bucket=None, key=None ):
        pass



class S3Uploader(object):

    _resizer_config = None
    _s3_connection = None
    _s3_config = None
    _s3_logger = None
    _s3_saved = None
    
    s3headers_public_default = None
    s3headers_archive_default = None

    filename_template = "%(guid)s-%(suffix)s.%(format)s"



    def __init__( self , s3_config=None , s3_logger=None , resizer_config=None ):
        self._s3_config = s3_config
        self._s3_logger = s3_logger
        self._s3_saved = {}
        self._resizer_config = resizer_config

        ##
        ## generate the default headers
        ##
        # public and archive get different acls / content-types
        self.s3headers_public_default= { 'x-amz-acl' : 'public-read' }
        if self._s3_config.bucket_public_headers:
            for k in self._s3_config.bucket_public_headers:
                self.s3headers_public_default[k]= self._s3_config.bucket_public_headers[k]
        self.s3headers_archive_default= {}
        if self._s3_config.bucket_archive_headers:
            for k in self._s3_config.bucket_archive_headers:
                self.s3headers_archive_default[k]= self._s3_config.bucket_archive_headers[k]


    @property
    def s3_connection(self):
        """property that memoizes the connection"""
        if self._s3_connection is None:
            self._s3_connection = boto.connect_s3( self._s3_config.key_public , self._s3_config.key_private )
        return self._s3_connection
        
        
    def _validate__image_resizes_selected( self , resized_images , image_resizes_selected ):
        """shared validation
            returns `dict` image_resizes_selected
        """

        # default to the resized images
        if image_resizes_selected is None:
            image_resizes_selected = resized_images.keys()

        for k in image_resizes_selected :

            if k not in resized_images :
                raise errors.ImageError_ConfigError("selected size is not resized_images (%s)" % k)
        
            if k not in self._resizer_config.image_resizes :
                raise errors.ImageError_ConfigError("selected size is not self._resizer_config.image_resizes (%s)" % k)
        
            # exist early for invalid sizes
            if k[0] == "@" :
                raise errors.ImageError_ConfigError("@ is a reserved initial character for image sizes (%s)" % k)
        
        return image_resizes_selected
        


    def setup_s3_buckets( self , s3_archive_original=None  ):
        """configures connections to relevant s3 buckets"""

        # create our bucket list 
        s3_buckets= {}

        # are we archiving the original ?        
        s3_archive_original = s3_archive_original
        if s3_archive_original is None :
            s3_archive_original = self._s3_config.archive_original

        # @public and @archive are special
        bucket_public = boto.s3.bucket.Bucket( connection=self.s3_connection , name=self._s3_config.bucket_public_name )
        s3_buckets[self._s3_config.bucket_public_name] = bucket_public
        s3_buckets['@public'] = bucket_public
        if s3_archive_original :
            bucket_archive = boto.s3.bucket.Bucket( connection=self.s3_connection , name=self._s3_config.bucket_archive_name )
            s3_buckets[self._s3_config.bucket_archive_name] = bucket_archive
            s3_buckets['@archive'] = bucket_archive

        # look through our selected sizes
        for size in self._resizer_config.image_resizes_selected:
            if size[0] == "@":
                raise errors.ImageError_ConfigError("@ is a reserved initial character for image sizes")

            if 's3_bucket_public' in self._resizer_config.image_resizes[size]:
                bucket_name = self._resizer_config.image_resizes[size]['s3_bucket_public']
                if bucket_name not in s3_buckets :
                    s3_buckets[bucket_name] = boto.s3.bucket.Bucket( connection=self.s3_connection , name=bucket_name )

        # return the buckets
        return s3_buckets
    


    def s3_save( self , resized_images , guid=None, image_resizes_selected=None ,  archivalFile=None ):
        """
            Returns a dict of resized images
            calls self.register_image_file() if needed
            
            this resizes the images. 
            it returns the images and updates the internal dict.
            
            `resized_images`
                a `dict` of images that were resized
                
            `guid`
                a `uuid` or similar name that forms the basis for storage
                the guid is passed into the template in self._resizer_config
            
            `image_resizes_selected`
                a `list` of keys to save
                we default to saving all the resized images
            
            `s3_archive_original`
                default = `False`
                should we save the original ?
            
        """
        if guid is None:
            raise errors.ImageError_ArgsError("""You must supply a `guid` for 
            the image. this is used""")
            
        # quickly validate
        image_resizes_selected = self._validate__image_resizes_selected( resized_images , image_resizes_selected )

        # setup the s3 connection
        s3_buckets = self.setup_s3_buckets( s3_archive_original = bool(archivalFile) )

        # log uploads for removal/tracking and return           
        s3_uploads= {}

        # and then we have the bucketed filenames...
        target_filenames = self.s3_generate_filenames( resized_images , guid=guid , image_resizes_selected=image_resizes_selected )
        
        def derive_target( size ):
            for bucket_name in target_filenames.keys() :
                if size in target_filenames[ bucket_name ]:
                    return ( bucket_name , target_filenames[ bucket_name ][ size ] )
            raise ValueError('unknown target')

        try:

            # and then we upload...
            for size in image_resizes_selected:

                ( bucket_name , target_filename ) = derive_target( size )
                bucket = s3_buckets[ bucket_name ]

                log.debug("Uploading %s to %s " % ( target_filename , bucket ))

                # generate the headers
                # this could get moved into init...
                _s3_headers= self.s3headers_public_default.copy()
                _s3_headers['Content-Type'] = utils.PIL_type_to_content_type( resized_images[size].format )
                if 's3_headers' in self._resizer_config.image_resizes[size]:
                    for k in self._resizer_config.image_resizes[size]['s3_headers']:
                        _s3_headers[k]= self._resizer_config.image_resizes[size]['s3_headers'][k]

                # upload 
                s3_key= boto.s3.key.Key( bucket )
                s3_key.key= target_filename
                s3_key.set_contents_from_string( resized_images[size].file.getvalue() , headers=_s3_headers )

                # log for removal/tracking & return
                if bucket_name not in s3_uploads:
                    s3_uploads[bucket_name]= {}
                s3_uploads[bucket_name][size]= target_filename

                # log to external plugin too
                if self._s3_logger:
                    self._s3_logger.log_upload( bucket=bucket_name , key=target_filename )

            if archivalFile :
            
                size = "@archive"

                bucket_name= self._s3_config.bucket_archive_name
                bucket= s3_buckets[ bucket_name ]
                
                # calculate the suffix
                original_image_suffix= utils.PIL_type_to_standardized( self.imageObject.format )
                target_filename= "%s.%s" % ( guid , original_image_suffix )

                log.debug("Uploading %s to %s " % ( target_filename , bucket_name ))

                # calculate the headers ; 
                # no need to set acl, its going to be owner-only by default
                _s3_headers= self.s3headers_archive_default.copy()
                _s3_headers['Content-Type'] = utils.PIL_type_to_content_type( self.imageObject.format )

                # upload 
                s3_key_original= boto.s3.key.Key( bucket )
                s3_key_original.key= target_filename
                s3_key_original.set_contents_from_string( archivalFile.getvalue() , headers=_s3_headers )

                # log for removal/tracking & return
                if bucket_name not in s3_uploads:
                    s3_uploads[bucket_name]= {}
                s3_uploads[bucket_name][size]= target_filename

                # log to external plugin too
                if self._s3_logger:
                    self._s3_logger.log_upload( bucket=bucket_name , key=target_filename )

        except Exception as e :
            # if we have ANY issues, we want to delete everything from amazon s3. otherwise this stuff is just hiding up there
            log.debug("Error uploading... rolling back s3 items")
            s3_uploads = self.s3_delete_files( s3_buckets=s3_buckets , s3_uploads=s3_uploads )
            raise
            raise ImageError_S3Upload('error uploading')
            
        ## migrate the s3uploads into the self.s3saved
        self._update_s3_saved( s3_uploads=s3_uploads , mode='upload' )
        return s3_uploads


    def _update_s3_saved( self, s3_uploads=None , mode=None ):
        if mode == 'upload':
            for bucket_name in s3_uploads.keys():
                if bucket_name not in self._s3_saved :
                   self._s3_saved[bucket_name]= {}
                for size in s3_uploads[bucket_name].keys():
                    self._s3_saved[bucket_name][size]= s3_uploads[bucket_name][size]
        elif mode == 'delete':
            for bucket_name in s3_uploads.keys():
                if bucket_name not in self._s3_saved :
                   pass
                for size in s3_uploads[bucket_name].keys():
                    if size in self._s3_saved[bucket_name]:
                        del self._s3_saved[bucket_name][size]
        

    def s3_delete_files( self , s3_buckets=None , s3_uploads=None ):
        """workhorse for deletion"""

        for bucket_name in s3_uploads.keys():

            # active bucket
            bucket = s3_buckets[bucket_name]
                
            # loop the sizes
            for size in s3_uploads[bucket_name].keys():

                # one file at a time...
                target_filename = s3_uploads[bucket_name][size]
                log.debug( "going to delete %s from %s(%s)" % (target_filename,bucket_name,bucket) )
                bucket.delete_key(target_filename)

                # external logging
                if self._s3_logger:
                    self._s3_logger.log_delete( bucket=bucket_name , key=target_filename )

                # internal cleanup
                del s3_uploads[bucket_name][size]

            # internal cleanup
            del s3_uploads[bucket_name]

        self._update_s3_saved( s3_uploads=s3_uploads , mode='delete' )

        return s3_uploads
    
    
    
    def s3_generate_filenames( self , resized_images , guid=None , image_resizes_selected=None , s3_original_filename=None ):
        """
            Returns a dict of resized image names
            generates the filenames s3 would save to; 
            this is useful when you're deleting previously created images

            `resized_images`
                a `dict` of images that were resized
                
            `guid`
                a `uuid` or similar name that forms the basis for storage
                the guid is passed into the template in self._resizer_config
            
            `image_resizes_selected`
                a `list` of keys to save
                we default to saving all the resized images
            
            `s3_original_filename`
                name of original file

        """
        if guid is None:
            raise errors.ImageError_ArgsError("""You must supply a `guid` for 
            the image. this is used""")

        # default to the resized images
        if image_resizes_selected is None:
            image_resizes_selected = resized_images.keys()

        # quickly validate
        image_resizes_selected = self._validate__image_resizes_selected( resized_images , image_resizes_selected )


        # init our return dict
        s3_uploads= {}
        for size in image_resizes_selected:
        
            instructions = self._resizer_config.image_resizes[size]

            # calc vars for filename templating                
            filename_template = self.filename_template
            suffix = size
            if 'filename_template' in instructions:
                filename_template = instructions['filename_template']
            if 'suffix' in instructions:
                suffix = instructions['suffix']

            # generate the filename
            target_filename =  filename_template % {\
                    'guid' : guid , 
                    'suffix' : suffix , 
                    'format' : utils.PIL_type_to_standardized( resized_images[size].format ) 
                }

            # figure out the bucketname
            bucket_name = self._s3_config.bucket_public_name
            if 's3_bucket_public' in instructions :
                bucket_name = instructions['s3_bucket_public']

            if bucket_name not in s3_uploads:
                s3_uploads[bucket_name]= {}

            if size in s3_uploads[bucket_name]:
                raise errors.ImageError_ConfigError('multiple sizes are mapped to a single file')

            s3_uploads[bucket_name][size]= target_filename

        if s3_original_filename :
            bucket_name = self._s3_config.bucket_archive_name
            if bucket_name not in s3_uploads:
                s3_uploads[bucket_name] = {}
            target_filename = s3_original_filename
            s3_uploads[bucket_name]["@archive"] = target_filename

        ## return the filemapping
        return s3_uploads
    
