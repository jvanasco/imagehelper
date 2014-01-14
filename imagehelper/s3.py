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

    def log_upload( self, bucket_name=None, key=None , file_size=None , file_md5=None , ):
        """args:
        `self`
        `bucket_name`
            s3 bucket name
        `key`
            key in bucket
        `file_size`
            size in bytes
        `file_md5`
            hexdigest
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


class S3ManagerFactory(object):
    """Factory for generating S3Manager instances"""
    _resizerConfig = None
    _s3Config = None
    _s3Logger = None

    def __init__( self , s3Config=None , s3Logger=None , resizerConfig=None ):
        self._s3Config = s3Config
        self._s3Logger = s3Logger
        self._resizerConfig = resizerConfig
    
    def s3_manager(self):
        """generate and return a new S3Manager instance"""
        return S3Manager( s3Config=self._s3Config , s3Logger=self._s3Logger , resizerConfig=self._resizerConfig )

    def s3_simple_access(self):
        """generate and return a new S3SimpleAccess instance"""
        return S3SimpleAccess( s3Config=self._s3Config , s3Logger=self._s3Logger , resizerConfig=self._resizerConfig )
        
        


class _S3CoreManager(object):

    _resizerConfig = None
    _s3Config = None
    _s3Connection = None
    _s3Logger = None
    _s3_buckets = None
    
    s3headers_public_default = None
    s3headers_archive_default = None

    filename_template = "%(guid)s-%(suffix)s.%(format)s"
    filename_template_archive = "%(guid)s.%(format)s"


    @property
    def s3_connection(self):
        """property that memoizes the connection"""
        if self._s3Connection is None:
            self._s3Connection = boto.connect_s3( self._s3Config.key_public , self._s3Config.key_private )
        return self._s3Connection


    @property
    def s3_buckets( self ):
        """property that memoizes the s3 buckets"""
        if self._s3_buckets is None:
            # memoize the buckets

            # create our bucket list 
            s3_buckets = {}

            # @public and @archive are special
            bucket_public = boto.s3.bucket.Bucket( connection=self.s3_connection , name=self._s3Config.bucket_public_name )
            s3_buckets[self._s3Config.bucket_public_name] = bucket_public
            s3_buckets['@public'] = bucket_public
            if self._s3Config.bucket_archive_name :
                bucket_archive = boto.s3.bucket.Bucket( connection=self.s3_connection , name=self._s3Config.bucket_archive_name )
                s3_buckets[self._s3Config.bucket_archive_name] = bucket_archive
                s3_buckets['@archive'] = bucket_archive

            # look through our selected sizes
            if self._resizerConfig :
                for size in self._resizerConfig.selected_resizes:
                    if size[0] == "@":
                        raise errors.ImageError_ConfigError("@ is a reserved initial character for image sizes")

                    if 's3_bucket_public' in self._resizerConfig.resizesSchema[size]:
                        bucket_name = self._resizerConfig.resizesSchema[size]['s3_bucket_public']
                        if bucket_name not in s3_buckets :
                            s3_buckets[bucket_name] = boto.s3.bucket.Bucket( connection=self.s3_connection , name=bucket_name )
            
            # store the buckets
            self._s3_buckets = s3_buckets

        # return the memoized buckets
        return self._s3_buckets        


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
            if self._s3Logger:
                self._s3Logger.log_delete( bucket_name=bucket_name , 
                    key=target_filename , )

            # internal cleanup
            del s3_uploads[size]

        return s3_uploads
    

class S3Manager(_S3CoreManager):
    """`S3Manager` handles all the actual uploading and deleting"""

    def __init__( self , s3Config=None , s3Logger=None , resizerConfig=None ):
        if not resizerConfig :
            raise ValueError("""`S3Manager` requires a `resizerConfig` which contains the resize recipes. these are needed for generating filenames.""")
        self._s3Config = s3Config
        self._s3Logger = s3Logger
        self._resizerConfig = resizerConfig

        ##
        ## generate the default headers
        ##
        # public and archive get different acls / content-types
        self.s3headers_public_default = { 'x-amz-acl' : 'public-read' }
        if self._s3Config.bucket_public_headers:
            for k in self._s3Config.bucket_public_headers:
                self.s3headers_public_default[k]= self._s3Config.bucket_public_headers[k]
        self.s3headers_archive_default = {}
        if self._s3Config.bucket_archive_headers:
            for k in self._s3Config.bucket_archive_headers:
                self.s3headers_archive_default[k]= self._s3Config.bucket_archive_headers[k]

        
    def _validate__selected_resizes( self , resizerResultset , selected_resizes ):
        """shared validation
            returns `dict` selected_resizes

        ARGS
            `resizerResultset`
                `resizer.ResizerResultset` object 
                    `resized` - dict of images that were resized
                    `original ` - original file

            `selected_resizes`
                iterable of selected resizes

        """

        # default to the resized images
        if selected_resizes is None:
            selected_resizes = resizerResultset.resized.keys()

        for k in selected_resizes :

            if k not in resizerResultset.resized :
                raise errors.ImageError_ConfigError("selected size is not resizerResultset.resized (%s)" % k)
        
            if k not in self._resizerConfig.resizesSchema :
                raise errors.ImageError_ConfigError("selected size is not self._resizerConfig.resizesSchema (%s)" % k)
        
            # exist early for invalid sizes
            if ( k[0] == "@" ) :
                raise errors.ImageError_ConfigError("@ is a reserved initial character for image sizes (%s)" % k)
        
        return selected_resizes


    def generate_filenames( self , resizerResultset , guid , selected_resizes=None , archive_original=None ):
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
                the guid is passed into the template in self._resizerConfig
            
            `selected_resizes`
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
        if selected_resizes is None:
            selected_resizes = resizerResultset.resized.keys()

        # quickly validate
        selected_resizes = self._validate__selected_resizes(
            resizerResultset , selected_resizes )

        # init our return dict
        filename_mapping = {}

        for size in selected_resizes:
        
            instructions = self._resizerConfig.resizesSchema[size]

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
                    'format' : utils.PIL_type_to_standardized( instructions['format'] ) 
                }

            # figure out the bucketname
            bucket_name = self._s3Config.bucket_public_name
            if 's3_bucket_public' in instructions :
                bucket_name = instructions['s3_bucket_public']
                
            filename_mapping[ size ] = ( target_filename , bucket_name )
        
        if check_archive_original( resizerResultset , archive_original=archive_original )  :
            filename_template_archive = self.filename_template_archive
            target_filename = filename_template_archive % {\
                    'guid' : guid , 
                    'format' : utils.PIL_type_to_standardized( resizerResultset.original.format ) 
                }
            bucket_name = self._s3Config.bucket_archive_name
            filename_mapping["@archive"] = ( target_filename , bucket_name )

        ## return the filemapping
        return filename_mapping
    

    def s3_save( self , resizerResultset , guid , selected_resizes=None , archive_original=None ):
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
            
            `selected_resizes`
                default = `None` -- all keys of resizerResultset.resized
                a `list` of keys to save
                we default to saving all the resized images
                if you don't want to resize any images:
                    pass in an empty list -- []
                    passing in `None` will run the default images
            
            `archive_original`
                default = `None`
                should we archive the original ?
                implicit/explicit archival option.  see `def check_archive_original`

        """
        if guid is None:
            raise errors.ImageError_ArgsError("""You must supply a `guid` for 
            the image. this is used""")
            
        # quickly validate
        selected_resizes = self._validate__selected_resizes( 
            resizerResultset , selected_resizes )
            
        # setup the s3 connection
        s3_buckets = self.s3_buckets

        # and then we have the bucketed filenames...
        target_filenames = self.generate_filenames( resizerResultset , guid , 
            selected_resizes=selected_resizes , 
            archive_original=archive_original )
            
        # log uploads for removal/tracking and return           
        s3_uploads = {}
        try:

            # and then we upload...
            for size in selected_resizes:
            
                ( target_filename , bucket_name ) = target_filenames[ size ]
                bucket = s3_buckets[ bucket_name ]

                log.debug("Uploading %s to %s " % ( target_filename , bucket ))

                # generate the headers
                _s3_headers = self.s3headers_public_default.copy()
                _s3_headers['Content-Type'] = utils.PIL_type_to_content_type( resizerResultset.resized[size].format )
                if 's3_headers' in self._resizerConfig.resizesSchema[size]:
                    for k in self._resizerConfig.resizesSchema[size]['s3_headers']:
                        _s3_headers[k]= self._resizerConfig.resizesSchema[size]['s3_headers'][k]

                # upload 
                s3_key = boto.s3.key.Key( bucket )
                s3_key.key = target_filename
                s3_key.set_contents_from_string( resizerResultset.resized[size].file.getvalue() , headers=_s3_headers )
                

                # log for removal/tracking & return
                s3_uploads[size] = ( target_filename , bucket_name )

                # log to external plugin too
                if self._s3Logger:
                    self._s3Logger.log_upload( bucket_name = bucket_name , 
                        key = target_filename , 
                        file_size = resizerResultset.resized[size].file_size , 
                        file_md5 = resizerResultset.resized[size].file_md5 , 
                    )

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
                if self._s3Logger:
                    self._s3Logger.log_upload( bucket_name = bucket_name , 
                        key = target_filename , 
                        file_size = resizerResultset.original.file_size , 
                        file_md5 = resizerResultset.original.file_md5 , 
                    )
                        
        except Exception as e :
            # if we have ANY issues, we want to delete everything from amazon s3. otherwise this stuff is just hiding up there
            log.debug("Error uploading... rolling back s3 items")
            s3_uploads = self.s3_delete( s3_uploads )
            raise
            raise ImageError_S3Upload('error uploading')
            
        return s3_uploads





class S3SimpleAccess(_S3CoreManager):

    def __init__( self , s3Config=None , s3Logger=None , resizerConfig=None ):
        self._s3Config = s3Config
        self._s3Logger = s3Logger
        self._resizerConfig = resizerConfig

        ##
        ## generate the default headers
        ##
        # public and archive get different acls / content-types
        self.s3headers_public_default = { 'x-amz-acl' : 'public-read' }
        if self._s3Config.bucket_public_headers:
            for k in self._s3Config.bucket_public_headers:
                self.s3headers_public_default[k]= self._s3Config.bucket_public_headers[k]
        self.s3headers_archive_default = {}
        if self._s3Config.bucket_archive_headers:
            for k in self._s3Config.bucket_archive_headers:
                self.s3headers_archive_default[k]= self._s3Config.bucket_archive_headers[k]
    
    
    def s3_file_upload( self , bucket_name , filename , wrappedFile , upload_type="public"):
        if upload_type not in ( "public", "archive"):
            raise ValueError("upload_type must be `public` or `archive`")

        s3_buckets = self.s3_buckets
        s3_uploads = {}
        try:
        
            bucket = s3_buckets[ bucket_name ]

            log.debug("Uploading %s to %s " % ( filename , bucket_name ))

            # calculate the headers ; 
            # no need to set acl, its going to be owner-only by default
            _s3_headers = self.s3headers_public_default.copy()
            _s3_headers['Content-Type'] = utils.PIL_type_to_content_type( wrappedFile.format )

            # upload 
            s3_key_original = boto.s3.key.Key( bucket )
            s3_key_original.key = filename
            s3_key_original.set_contents_from_string( wrappedFile.file.getvalue() , headers=_s3_headers )

            # log for removal/tracking & return
            s3_uploads = self.simple_uploads_mapping( bucket_name , filename )

            # log to external plugin too
            if self._s3Logger:
                self._s3Logger.log_upload( bucket_name = bucket_name , 
                    key = filename , 
                    file_size = wrappedFile.file_size , 
                    file_md5 = wrappedFile.file_md5 , 
                )
                
            return s3_uploads
        except:
            raise
            
    def simple_uploads_mapping( self , bucket_name , filename ) :
        s3_uploads = {}
        s3_uploads[ "%s||%s" % (bucket_name,filename,) ] = ( filename , bucket_name )
        return s3_uploads


