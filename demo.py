import imagehelper
import cStringIO
import uuid

import ConfigParser
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


resizesSchema= {
    'thumb1': {
        'width': 120,
        'height': 120,
        'save_quality': 50,
        'suffix': 't1',
        'format':'JPEG',
        'constraint-method': 'fit-within',
        's3_bucket_public': AWS_BUCKET_ALT,
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

resizesSchema_alt= {
    'og:image': {
        'width': 3200,
        'height': 3200,
        'save_quality': 50,
        'suffix': 'og',
        'format':'JPEG',
        'constraint-method': 'smallest:ensure-minimum',
        'filename_template': '%(guid)s-og.%(format)s',
    },
    'og:image2': {
        'width': 200,
        'height': 200,
        'save_quality': 50,
        'suffix': 'og',
        'format':'JPEG',
        'constraint-method': 'smallest:ensure-minimum',
        'filename_template': '%(guid)s-og.%(format)s',
    },
    'og:image3': {
        'width': 300,
        'height': 200,
        'save_quality': 50,
        'suffix': 'og',
        'format':'JPEG',
        'constraint-method': 'smallest:ensure-minimum',
        'filename_template': '%(guid)s-og.%(format)s',
    },
}


class CustomS3Logger( imagehelper.s3.S3Logger ):
    def log_upload( self, bucket_name=None, key=None , file_size=None , file_md5=None ):
        print "CustomS3Logger.log_upload"
        print "\t %s , %s , %s , %s" % ( bucket_name , key , file_size , file_md5 )
    def log_delete( self, bucket_name=None, key=None ):
        print "CustomS3Logger.log_delete"
        print "\t %s , %s" % ( bucket_name , key )


s3Logger = CustomS3Logger()
resizerConfig = imagehelper.resizer.ResizerConfig( resizesSchema=resizesSchema , selected_resizes=selected_resizes )

# create a factory
resizerFactory = imagehelper.resizer.ResizerFactory( resizerConfig=resizerConfig )


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

    
guid= '123'


def demo_direct():
    "demo calling direct methods"
    

    resizer = resizerFactory.resizer()

    # try to register the image
    resizer.register_image_file( imagefile=get_imagefile() )
    
    try:
        # resize the image
        # this should fail, because we don't want to risk changing the image before registering
        results = resizer.resize( imagefile=get_imagefile() )
    except imagehelper.errors.ImageError_DuplicateAction :
        # expected!
        pass
        

    resizer = resizerFactory.resizer( imagefile=get_imagefile() )
    resizedImages = resizer.resize()
    
    print resizedImages
    

def demo_factory():
    "demo calling factory methods"
    
    # resize !
    resizer = resizerFactory.resizer( imagefile=get_imagefile() )
    resizedImages = resizer.resize()


def demo_s3():
    "demo s3 uploading"

    resizer = resizerFactory.resizer( imagefile=get_imagefile() )
    resizedImages = resizer.resize()

    # upload the resized items
    uploader = imagehelper.s3.S3Manager( s3Config=s3Config , resizerConfig=resizerConfig , s3Logger=s3Logger )
    uploaded = uploader.s3_save( resizedImages , guid )
    print "uploaded! %s" % uploaded
    
    deleted = uploader.s3_delete( uploaded )
    print "deleted! %s" % deleted
    

def demo_s3_alt():
    "demo s3 uploading"

    resizer = resizerFactory.resizer( imagefile=get_imagefile() )
    resizedImages = resizer.resize()

    # upload the resized items
    uploader = imagehelper.s3.S3Manager( s3Config=s3Config , resizerConfig=resizerConfig , s3Logger=s3Logger )
    uploaded_original = uploader.s3_save( resizedImages , guid , selected_resizes=[] , archive_original=True )
    print "uploaded_original! %s" % uploaded_original

    uploaded_resizes = uploader.s3_save( resizedImages , guid , archive_original=False )
    print "uploaded_resizes! %s" % uploaded_resizes
    
    uploaded_all = dict( uploaded_original.items() + uploaded_resizes.items() )
    
    deleted = uploader.s3_delete( uploaded_all )
    print "deleted! %s" % deleted
    
    
def demo_alt_resizing():

    resizerConfig = imagehelper.resizer.ResizerConfig( resizesSchema=resizesSchema_alt )

    # build a factory & resize
    resizerFactory= imagehelper.resizer.ResizerFactory( resizerConfig=resizerConfig )
    resizedImages = resizerFactory.resize( imagefile=get_imagefile() )
    
    print resizedImages
    

def demo_md5():
    "demo file md5"
    
    # resize !
    resizer = resizerFactory.resizer( imagefile=get_imagefile() )
    resizedImages = resizer.resize()
    
    print resizedImages
    for k in resizedImages.resized.keys() :
        print resizedImages.resized[k].file_md5

    print resizedImages.original.file_md5
    print resizedImages.original.file_size


def demo_serialze():
    "demo file serialize"
    
    # resize !
    resizer = resizerFactory.resizer( imagefile=get_imagefile() )
    
    file_md5 = resizer.get_original().file_md5
    file_b64 = resizer.get_original().file_b64

    resizer = resizerFactory.resizer( file_b64 = file_b64 )
    



if True:
    pass
    demo_direct()
    demo_factory()
    demo_s3()
    demo_s3_alt()
    demo_md5()
    demo_serialze()

if False:
    pass

