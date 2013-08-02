import imagehelper

import unittest
import ConfigParser
import cStringIO


resizesSchema= {
    'thumb1': {
        'width': 120,
        'height': 120,
        'save_quality': 50,
        'suffix': 't1',
        'format':'JPEG',
        'constraint-method': 'fit-within',
        'filename_template': '%(guid)s.%(format)s',
        's3_headers': { 'x-amz-acl' : 'public-read' }
    },
    't2': {
        'width': 120,
        'height': 120,
        'save_quality': 50,
        'suffix': 't2',
        'format':'PDF',
        'constraint-method': 'fit-within:ensure-width',
    },
    'thumb3': {
        'width': 120,
        'height': 120,
        'format':'GIF',
        'constraint-method': 'fit-within:ensure-height',
    },
    't4': {
        'width': 120,
        'height': 120,
        'save_optimize': True,
        'filename_template': '%(guid)s---%(suffix)s.%(format)s',
        'suffix': 't4',
        'format':'PNG',
        'constraint-method': 'fit-within:crop-to',
    },
}
selected_resizes = ['thumb1','t2','thumb3','t4']

_img = None
def get_imagefile():
    global _img
    if _img is  None:
        img = open('tests/henry.jpg','r')
        img.seek(0)
        data = img.read()
        img.close()
        img2 = cStringIO.StringIO()
        img2.write(data)
        _img = img2
    _img.seek(0)
    return _img


def newS3Config():
    Config = ConfigParser.ConfigParser()
    Config.read('aws.cfg')
    AWS_KEY_PUBLIC = Config.get('aws','AWS_KEY_PUBLIC')
    AWS_KEY_SECRET = Config.get('aws','AWS_KEY_SECRET')
    AWS_BUCKET_PUBLIC = Config.get('aws','AWS_BUCKET_PUBLIC')
    AWS_BUCKET_SECRET = Config.get('aws','AWS_BUCKET_SECRET')
    AWS_BUCKET_ALT = Config.get('aws','AWS_BUCKET_ALT')
    
    s3Config= imagehelper.s3.S3Config(
        key_public = AWS_KEY_PUBLIC,
        key_private = AWS_KEY_SECRET,
        bucket_public_name = AWS_BUCKET_PUBLIC,
        bucket_archive_name = AWS_BUCKET_SECRET,
        bucket_public_headers = { 'x-amz-acl' : 'public-read' },
        bucket_archive_headers = { },
        archive_original = True
    )
    
    return s3Config
    
def newResizerConfig():
    resizerConfig = imagehelper.resizer.ResizerConfig( resizesSchema=resizesSchema , selected_resizes=selected_resizes )
    return resizerConfig


def newS3Logger():
    s3Logger = imagehelper.s3.S3Logger()
    return s3Logger



class CustomS3Logger( imagehelper.s3.S3Logger ):
    def log_upload( self, bucket_name=None, key=None , file_size=None , file_md5=None ):
        print "CustomS3Logger.log_upload"
        print "\t %s , %s , %s , %s" % ( bucket_name , key , file_size , file_md5 )
    def log_delete( self, bucket_name=None, key=None ):
        print "CustomS3Logger.log_delete"
        print "\t %s , %s" % ( bucket_name , key )



class TestResize( unittest.TestCase ):

    def test_direct_resize(self):
    
        # new resizer config
        resizerConfig = newResizerConfig()
    
        # build a new resizer
        resizer = imagehelper.resizer.Resizer( resizerConfig=resizerConfig )

        # try to register the image
        resizer.register_image_file( imagefile=get_imagefile() )
    
        try:
            # resize the image
            # this should fail, because we don't want to risk changing the image before registering
            results = resizer.resize( imagefile=get_imagefile() )
        except imagehelper.errors.ImageError_DuplicateAction :
            # expected!
            pass
        
        # build a new resizer
        resizer = imagehelper.resizer.Resizer( resizerConfig=resizerConfig )
        # resize the image
        resizedImages = resizer.resize( imagefile=get_imagefile() )



class TestS3( unittest.TestCase ):

    def test_s3_factory(self):

        # generate the configs    
        resizerConfig = newResizerConfig()
        s3Config = newS3Config()
        s3Logger = newS3Logger()
        
        # generate the factory
        s3ManagerFactory = imagehelper.s3.S3ManagerFactory( s3Config=s3Config , s3Logger=s3Logger , resizerConfig=resizerConfig )
        
        # grab a manager
        s3Manager = s3ManagerFactory.s3_manager()
        
        # make sure we generated a manager
        assert isinstance( s3Manager , imagehelper.s3.S3Manager )   

        # inspect the manager to ensure it is set up correctly
        assert s3Manager._s3Config == s3Config 
        assert s3Manager._s3Logger == s3Logger 
        assert s3Manager._resizerConfig == resizerConfig 



    def test_s3(self):
    
        # new resizer config
        resizerConfig = newResizerConfig()
        # build a factory
        resizerFactory = imagehelper.resizer.ResizerFactory( resizerConfig=resizerConfig )
        
        # grab a resizer
        resizer = resizerFactory.resizer()
        
        # resize !
        resizedImages = resizer.resize( imagefile=get_imagefile() )

        # new s3 config
        s3Config = newS3Config()
        # new s3 logger
        if False :
            s3Logger = imagehelper.s3.S3Logger()
        else:
            s3Logger = CustomS3Logger()

        # upload the resized items
        uploader = imagehelper.s3.S3Manager( s3Config=s3Config , resizerConfig=resizerConfig , s3Logger=s3Logger )
        
        guid = "123"
        uploaded = uploader.s3_save( resizedImages , guid )
        deleted = uploader.s3_delete( uploaded )


class TestResizingMethods( unittest.TestCase ):

    def test_fit_within(self):
        method = 'fit-within'
        schema = {
            'test': {
                'width': 120,
                'height': 120,
                'save_optimize': True,
                'format':'PNG',
                'constraint-method': method,
            },
        }
        
        ## what do we expect ?
        expected_original_wh = ( 1200 , 1600 )
        expected_resized_wh = ( 90 , 120 )

        r = imagehelper.resizer.Resizer()
        results = r.resize( imagefile=get_imagefile() , resizesSchema=schema , selected_resizes=('test',) )
        
        ## what do we have ?
        actual_original_wh = ( results.original.width , results.original.height )
        actual_resized_wh = ( results.resized['test'].width , results.resized['test'].height )

        ## assert the original matches
        assert expected_original_wh[0] == actual_original_wh[0]
        assert expected_original_wh[1] == actual_original_wh[1]

        ## assert the resize matches
        assert expected_resized_wh[0] == actual_resized_wh[0]
        assert expected_resized_wh[1] == actual_resized_wh[1]
        

    def test_fit_within_crop_to(self):
        method = 'fit-within:crop-to'
        schema = {
            'test': {
                'width': 120,
                'height': 120,
                'save_optimize': True,
                'format':'PNG',
                'constraint-method': method,
            },
        }
        
        ## what do we expect ?
        expected_original_wh = ( 1200 , 1600 )
        expected_resized_wh = ( 120 , 120 )

        r = imagehelper.resizer.Resizer()
        results = r.resize( imagefile=get_imagefile() , resizesSchema=schema , selected_resizes=('test',) )
        
        ## what do we have ?
        actual_original_wh = ( results.original.width , results.original.height )
        actual_resized_wh = ( results.resized['test'].width , results.resized['test'].height )

        ## assert the original matches
        assert expected_original_wh[0] == actual_original_wh[0]
        assert expected_original_wh[1] == actual_original_wh[1]

        ## assert the resize matches
        assert expected_resized_wh[0] == actual_resized_wh[0]
        assert expected_resized_wh[1] == actual_resized_wh[1]


    def test_fit_within_ensure_width(self):
        method = 'fit-within:ensure-width'
        schema = {
            'test': {
                'width': 120,
                'height': 120,
                'save_optimize': True,
                'format':'PNG',
                'constraint-method': method,
            },
        }
        
        ## what do we expect ?
        expected_original_wh = ( 1200 , 1600 )
        expected_resized_wh = ( 120 , 160 )

        r = imagehelper.resizer.Resizer()
        results = r.resize( imagefile=get_imagefile() , resizesSchema=schema , selected_resizes=('test',) )
        
        ## what do we have ?
        actual_original_wh = ( results.original.width , results.original.height )
        actual_resized_wh = ( results.resized['test'].width , results.resized['test'].height )

        ## assert the original matches
        assert expected_original_wh[0] == actual_original_wh[0]
        assert expected_original_wh[1] == actual_original_wh[1]

        ## assert the resize matches
        assert expected_resized_wh[0] == actual_resized_wh[0]
        assert expected_resized_wh[1] == actual_resized_wh[1]
        

    def test_fit_within_ensure_height(self):
        method = 'fit-within:ensure-height'
        schema = {
            'test': {
                'width': 120,
                'height': 120,
                'save_optimize': True,
                'format':'PNG',
                'constraint-method': method,
            },
        }
        
        ## what do we expect ?
        expected_original_wh = ( 1200 , 1600 )
        expected_resized_wh = ( 90 , 120 )

        r = imagehelper.resizer.Resizer()
        results = r.resize( imagefile=get_imagefile() , resizesSchema=schema , selected_resizes=('test',) )
        
        ## what do we have ?
        actual_original_wh = ( results.original.width , results.original.height )
        actual_resized_wh = ( results.resized['test'].width , results.resized['test'].height )

        ## assert the original matches
        assert expected_original_wh[0] == actual_original_wh[0]
        assert expected_original_wh[1] == actual_original_wh[1]

        ## assert the resize matches
        assert expected_resized_wh[0] == actual_resized_wh[0]
        assert expected_resized_wh[1] == actual_resized_wh[1]


    def test_fit_within_smallest_ensure_minimum(self):
        method = 'smallest:ensure-minimum'
        schema = {
            'test': {
                'width': 120,
                'height': 120,
                'save_optimize': True,
                'format':'PNG',
                'constraint-method': method,
            },
        }
        
        ## what do we expect ?
        expected_original_wh = ( 1200 , 1600 )
        expected_resized_wh = ( 120 , 160 )

        r = imagehelper.resizer.Resizer()
        results = r.resize( imagefile=get_imagefile() , resizesSchema=schema , selected_resizes=('test',) )
        
        ## what do we have ?
        actual_original_wh = ( results.original.width , results.original.height )
        actual_resized_wh = ( results.resized['test'].width , results.resized['test'].height )

        ## assert the original matches
        assert expected_original_wh[0] == actual_original_wh[0]
        assert expected_original_wh[1] == actual_original_wh[1]

        ## assert the resize matches
        assert expected_resized_wh[0] == actual_resized_wh[0]
        assert expected_resized_wh[1] == actual_resized_wh[1]


    def test_fit_within_exact_no_resize(self):
        method = 'exact:no-resize'
        schema = {
            'test': {
                'width': 1200,
                'height': 1600,
                'save_optimize': True,
                'format':'PNG',
                'constraint-method': method,
            },
        }
        
        ## what do we expect ?
        expected_original_wh = ( 1200 , 1600 )
        expected_resized_wh = ( 1200 , 1600 )

        r = imagehelper.resizer.Resizer()
        results = r.resize( imagefile=get_imagefile() , resizesSchema=schema , selected_resizes=('test',) )

        ## what do we have ?
        actual_original_wh = ( results.original.width , results.original.height )
        actual_resized_wh = ( results.resized['test'].width , results.resized['test'].height )

        ## assert the original matches
        assert expected_original_wh[0] == actual_original_wh[0]
        assert expected_original_wh[1] == actual_original_wh[1]

        ## assert the resize matches
        assert expected_resized_wh[0] == actual_resized_wh[0]
        assert expected_resized_wh[1] == actual_resized_wh[1]


    def test_fit_within_exact_proportion(self):
        method = 'exact:proportion'
        schema = {
            'test': {
                'width': 240,
                'height': 320,
                'save_optimize': True,
                'format':'PNG',
                'constraint-method': method,
            },
        }
        
        ## what do we expect ?
        expected_original_wh = ( 1200 , 1600 )
        expected_resized_wh = ( 240 , 320 )

        r = imagehelper.resizer.Resizer()
        results = r.resize( imagefile=get_imagefile() , resizesSchema=schema , selected_resizes=('test',) )

        ## what do we have ?
        actual_original_wh = ( results.original.width , results.original.height )
        actual_resized_wh = ( results.resized['test'].width , results.resized['test'].height )

        ## assert the original matches
        assert expected_original_wh[0] == actual_original_wh[0]
        assert expected_original_wh[1] == actual_original_wh[1]

        ## assert the resize matches
        assert expected_resized_wh[0] == actual_resized_wh[0]
        assert expected_resized_wh[1] == actual_resized_wh[1]



