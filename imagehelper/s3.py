import logging
log = logging.getLogger(__name__)

from . import errors
from . import utils

try:
    import boto
    import boto.s3
    import boto.s3.bucket
except:
    boto = None
    
    
def check_archive_original( resizerResultset , archive_original=None ):
    """do we want to archive the original?
    
    `resizerResultset`
        object of `resizer.Resultset`
    
    `archive_original`
        should we archive original?
        `None` (default)
            implicit
            archive if resizerResultset.original
        `True`
            explict.
            archive resizerResultset.original; 
            raise error if missing
        `False`
            explicit.
            do not archive.
    """

    if archive_original is False :
        return False

    elif archive_original is None :
        if resizerResultset.original :
            return True
        return False

    elif archive_original is True :
        if not resizerResultset.original :
            raise ValueError("""Missing resizerResultset.original for 
                explicit archiving""")
        return True



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

    def log_upload( self, bucket_name=None, key=None , filesize=None ):
        """args:
        `self`
        `bucket_name`
            s3 bucket name
        `key`
            key in bucket
        `filesize`
            size in bytes
        """
        pass

    def log_delete( self, bucket_name=None, key=None ):
        """args:
        `self`
        `bucket_name`
            s3 bucket name
        `key`
            key in bucket
        """
        pass



class S3Uploader(object):

    _resizer_config = None
    _s3_buckets = None
    _s3_connection = None
    _s3_config = None
    _s3_logger = None
    
    s3headers_public_default = None
    s3headers_archive_default = None

    filename_template = "%(guid)s-%(suffix)s.%(format)s"
    filename_template_archive = "%(guid)s.%(format)s"



    def __init__( self , s3_config=None , s3_logger=None , resizer_config=None ):
        self._s3_config = s3_config
        self._s3_logger = s3_logger
        self._resizer_config = resizer_config

        ##
        ## generate the default headers
        ##
        # public and archive get different acls / content-types
        self.s3headers_public_default = { 'x-amz-acl' : 'public-read' }
        if self._s3_config.bucket_public_headers:
            for k in self._s3_config.bucket_public_headers:
                self.s3headers_public_default[k]= self._s3_config.bucket_public_headers[k]
        self.s3headers_archive_default = {}
        if self._s3_config.bucket_archive_headers:
            for k in self._s3_config.bucket_archive_headers:
                self.s3headers_archive_default[k]= self._s3_config.bucket_archive_headers[k]


    @property
    def s3_connection(self):
        """property that memoizes the connection"""
        if self._s3_connection is None:
            self._s3_connection = boto.connect_s3( self._s3_config.key_public , self._s3_config.key_private )
        return self._s3_connection


    @property
    def s3_buckets( self ):
        """property that memoizes the s3 buckets"""
        if self._s3_buckets is None:
            # memoize the buckets

            # create our bucket list 
            s3_buckets = {}

            # @public and @archive are special
            bucket_public = boto.s3.bucket.Bucket( connection=self.s3_connection , name=self._s3_config.bucket_public_name )
            s3_buckets[self._s3_config.bucket_public_name] = bucket_public
            s3_buckets['@public'] = bucket_public
            if self._s3_config.archive_original :
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
            
            # store the buckets
            self._s3_buckets = s3_buckets

        # return the memoized buckets
        return self._s3_buckets        


        
    def _validate__image_resizes_selected( self , resizerResultset , image_resizes_selected ):
        """shared validation
            returns `dict` image_resizes_selected

        ARGS
            `resizerResultset`
                `resizer.ResizerResultset` object 
                    `resized` - dict of images that were resized
                    `original ` - original file

            `image_resizes_selected`
                iterable of selected resizes

        """

        # default to the resized images
        if image_resizes_selected is None:
            image_resizes_selected = resizerResultset.resized.keys()

        for k in image_resizes_selected :

            if k not in resizerResultset.resized :
                raise errors.ImageError_ConfigError("selected size is not resizerResultset.resized (%s)" % k)
        
            if k not in self._resizer_config.image_resizes :
                raise errors.ImageError_ConfigError("selected size is not self._resizer_config.image_resizes (%s)" % k)
        
            # exist early for invalid sizes
            if ( k[0] == "@" ) :
                raise errors.ImageError_ConfigError("@ is a reserved initial character for image sizes (%s)" % k)
        
        return image_resizes_selected
        



    def s3_save( self , resizerResultset , guid, image_resizes_selected=None , archive_original=None ):
        """
            Returns a dict of resized images
            calls self.register_image_file() if needed
            
            this resizes the images. 
            it returns the images and updates the internal dict.
            
            `resizerResultset`
                a `resizer.ResizerResultset` object 
                    `resized` - dict of images that were resized
                    `original ` - original file

            `guid`
                a `uuid` or similar name that forms the basis for storage
                the guid is passed to the template in `self.generate_filenames`
            
            `image_resizes_selected`
                default = `None` -- all keys of resizerResultset.resized
                a `list` of keys to save
                we default to saving all the resized images
            
            `archive_original`
                default = `None`
                should we archive the original ?
                implicit/explicit archival option.  see `def check_archive_original`

        """
        if guid is None:
            raise errors.ImageError_ArgsError("""You must supply a `guid` for 
            the image. this is used""")
            
        # quickly validate
        image_resizes_selected = self._validate__image_resizes_selected( 
            resizerResultset , image_resizes_selected )

        # setup the s3 connection
        s3_buckets = self.s3_buckets

        # and then we have the bucketed filenames...
        target_filenames = self.generate_filenames( resizerResultset , guid , 
            image_resizes_selected=image_resizes_selected , 
            archive_original=archive_original )
            
        # log uploads for removal/tracking and return           
        s3_uploads = {}
        try:

            # and then we upload...
            for size in image_resizes_selected:
            
                ( target_filename , bucket_name ) = target_filenames[ size ]
                bucket = s3_buckets[ bucket_name ]

                log.debug("Uploading %s to %s " % ( target_filename , bucket ))

                # generate the headers
                _s3_headers = self.s3headers_public_default.copy()
                _s3_headers['Content-Type'] = utils.PIL_type_to_content_type( resizerResultset.resized[size].format )
                if 's3_headers' in self._resizer_config.image_resizes[size]:
                    for k in self._resizer_config.image_resizes[size]['s3_headers']:
                        _s3_headers[k]= self._resizer_config.image_resizes[size]['s3_headers'][k]

                # upload 
                s3_key = boto.s3.key.Key( bucket )
                s3_key.key = target_filename
                s3_key.set_contents_from_string( resizerResultset.resized[size].file.getvalue() , headers=_s3_headers )
                

                # log for removal/tracking & return
                s3_uploads[size] = ( target_filename , bucket_name )

                # log to external plugin too
                if self._s3_logger:
                    self._s3_logger.log_upload( bucket_name=bucket_name , 
                        key=target_filename , 
                        filesize=resizerResultset.resized[size].filesize , )

            if '@archive' in target_filenames  :
            
                size = "@archive"
                ( target_filename , bucket_name ) = target_filenames[ size ]
                bucket = s3_buckets[ bucket_name ]

                log.debug("Uploading %s to %s " % ( target_filename , bucket_name ))

                # calculate the headers ; 
                # no need to set acl, its going to be owner-only by default
                _s3_headers = self.s3headers_archive_default.copy()
                _s3_headers['Content-Type'] = utils.PIL_type_to_content_type( resizerResultset.original.format )

                # upload 
                s3_key_original = boto.s3.key.Key( bucket )
                s3_key_original.key = target_filename
                s3_key_original.set_contents_from_string( resizerResultset.original.file.getvalue() , headers=_s3_headers )

                # log for removal/tracking & return
                s3_uploads[size] = ( target_filename , bucket_name )

                # log to external plugin too
                if self._s3_logger:
                    self._s3_logger.log_upload( bucket_name=bucket_name , 
                        key=target_filename , 
                        filesize=resizerResultset.original.filesize , )
                        
        except Exception as e :
            # if we have ANY issues, we want to delete everything from amazon s3. otherwise this stuff is just hiding up there
            log.debug("Error uploading... rolling back s3 items")
            s3_uploads = self.s3_delete( s3_uploads )
            raise
            raise ImageError_S3Upload('error uploading')
            
        return s3_uploads



    def s3_delete( self , s3_uploads ):
        """workhorse for deletion
        
            `s3_uploads` 
                `dict`
                format = 
                    s3_uploads[size] = ( target_filename , bucket_name )
        
        """

        # setup the s3 connection
        s3_buckets = self.s3_buckets

        for size in s3_uploads.keys():

            # grab the stash
            ( target_filename , bucket_name ) = s3_uploads[size]

            # active bucket
            bucket = s3_buckets[bucket_name]
                
            # delete it
            log.debug( "going to delete %s from %s" % (target_filename,bucket_name) )

            bucket.delete_key(target_filename)

            # external logging
            if self._s3_logger:
                self._s3_logger.log_delete( bucket_name=bucket_name , 
                    key=target_filename , )

            # internal cleanup
            del s3_uploads[size]

        return s3_uploads
    
    
    
    def generate_filenames( self , resizerResultset , guid , image_resizes_selected=None , archive_original=None ):
        """
            generates the filenames s3 would save to; 
            this is useful for planning/testing or deleting old files

            Returns a `dict` of target filenames
                keys = resized size
                values = tuple ( target_filename , bucket_name )
            
            `resizerResultset`
                a `resizer.ResizerResultset` object 
                    `resized` - dict of images that were resized
                    `original ` - original file

            `guid`
                a `uuid` or similar name that forms the basis for storage
                the guid is passed into the template in self._resizer_config
            
            `image_resizes_selected`
                default = `None` -- all keys of resizerResultset.resized
                a `list` of keys to save
                we default to saving all the resized images
            
            `archive_original`
                default = `None`
                should we archive the original ?
                implicit/explicit archival option.  see `def check_archive_original`

        """
        if guid is None:
            raise errors.ImageError_ArgsError("""You must supply a `guid` for 
            the image. this is used for filename templating""")

        # default to the resized images
        if image_resizes_selected is None:
            image_resizes_selected = resizerResultset.resized.keys()

        # quickly validate
        image_resizes_selected = self._validate__image_resizes_selected(
            resizerResultset , image_resizes_selected )

        # init our return dict
        filename_mapping = {}

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
                    'format' : utils.PIL_type_to_standardized( resizerResultset.resized[size].format ) 
                }

            # figure out the bucketname
            bucket_name = self._s3_config.bucket_public_name
            if 's3_bucket_public' in instructions :
                bucket_name = instructions['s3_bucket_public']
                
            filename_mapping[ size ] = ( target_filename , bucket_name )
        
        if check_archive_original( resizerResultset , archive_original=archive_original )  :
            filename_template_archive = self.filename_template_archive
            target_filename = filename_template_archive % {\
                    'guid' : guid , 
                    'format' : utils.PIL_type_to_standardized( resizerResultset.original.format ) 
                }
            bucket_name = self._s3_config.bucket_archive_name
            filename_mapping["@archive"] = ( target_filename , bucket_name )

        ## return the filemapping
        return filename_mapping
    
