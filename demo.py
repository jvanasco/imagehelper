import imagehelper
import cStringIO


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


image_resizes= {
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
image_resizes_selected = ['thumb1','t2','thumb3','t4']

s3Logger = imagehelper.s3.S3Logger()
rConfig = imagehelper.resizer.ResizerConfig( image_resizes=image_resizes , image_resizes_selected=image_resizes_selected )

# create a wrapper
resizer = imagehelper.resizer.Resizer( resizer_config=rConfig )


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
    
    # try to register the image
    resizer.register_image_file( imagefile=get_imagefile() )
    
    try:
        # resize the image
        # this should fail, because we don't want to risk changing the image before registering
        results = resizer.resize( imagefile=get_imagefile() )
    except imagehelper.errors.ImageError_DuplicateAction :
        # expected!
        pass
        
    # reset the resizer
    resizer.reset()
    
    # resize the image
    results = resizer.resize( imagefile=get_imagefile() )
    
    print results
    

def demo_factory():
    "demo calling factory methods"
    
    # build a factory
    rFactory= imagehelper.resizer.ResizerFactory( resizer_config=rConfig )

    # resize !
    results = rFactory.resize( imagefile=get_imagefile() )


def demo_s3():
    "demo s3 uploading"
    # build a factory & resize
    rFactory= imagehelper.resizer.ResizerFactory( resizer_config=rConfig )
    resized = rFactory.resize( imagefile=get_imagefile() )
    print resized
    
    uploader = imagehelper.s3.S3Uploader( s3_config=s3Config , resizer_config=rConfig )
    print uploader.s3_save( resized , guid=guid )



if True:
    pass
    demo_s3()

if False:
    pass
    demo_direct()
    demo_factory()


raise ValueError("ok")

if 0:
    # we'll pass in a guid.  in your code this would be the id in your database
    #saved= rFactory.resize(photofile=puppy,s3_save=True,s3_save_original=True,guid=guid,s3_logger=s3Logger)
    print saved.__dict__
    print saved.s3_saved[AWS_BUCKET_SECRET]

    # we'll pass in a guid.  in your code this would be the id in your database
    s3_filenames= rFactory.s3_generate_filenames( guid=guid , s3_original_filename=saved.s3_saved[AWS_BUCKET_SECRET]['@archive'] )
    print s3_filenames

if 1 :

    # we'll pass in a guid.  in your code this would be the id in your database
    s3_filenames= rFactory.s3_generate_filenames( guid=guid , s3_original_filename='123.jpg' )
    print s3_filenames
    
    s3_buckets= rFactory.setup_s3_buckets( s3_save_original=False )
    print s3_buckets

    s3_buckets= rFactory.setup_s3_buckets( s3_save_original=True )
    print s3_buckets
    
    print "delete..."
    print rFactory.s3_delete_files( s3_uploads=s3_filenames )
    
    print "deleted!"
    print rFactory.__dict__
    
    
