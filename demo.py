import imagehelper

import ConfigParser
Config = ConfigParser.ConfigParser()
Config.read('aws.cfg')
AWS_KEY_PUBLIC= Config.get('aws','AWS_KEY_PUBLIC')
AWS_KEY_SECRET= Config.get('aws','AWS_KEY_SECRET')
AWS_BUCKET_PUBLIC= Config.get('aws','AWS_BUCKET_PUBLIC')
AWS_BUCKET_SECRET= Config.get('aws','AWS_BUCKET_SECRET')

s3Config= imagehelper.S3Config(
    key_public= AWS_KEY_PUBLIC,
    key_private= AWS_KEY_SECRET,
    bucket_public_name= AWS_BUCKET_PUBLIC,
    bucket_archive_name= AWS_BUCKET_SECRET,
    bucket_public_headers= { 'x-amz-acl' : 'public-read' },
    bucket_archive_headers= { },
)


photo_resizes= {
    'thumb1': {
        'width': 120,
        'height': 120,
        'save_quality': 50,
        'suffix': 't1',
        'format':'JPEG',
        'constraint-method': 'fit-within',
        's3_bucket_public': 'my-test',
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
photo_resizes_selected= ['thumb1','t2','thumb3','t4']

s3Logger= imagehelper.S3Logger()
rConfig= imagehelper.ResizerConfig( photo_resizes=photo_resizes , photo_resizes_selected=photo_resizes_selected )
rFactory= imagehelper.ResizerFactory(resizer_config=rConfig,s3_config=s3Config)

puppy= open('tests/henry.jpg','r')




if 1:
    # direct route
    print "___ DIRECT ___"
    rWrapper= imagehelper.ResizerWrapper(resizer_config=rConfig)
    rWrapper.register_image_file(photofile=puppy)
    rWrapper.resize(photofile=puppy)
    print rWrapper.__dict__

if 1:
    # factory way
    print "___ FACTORY ___"
    wrapped= rFactory.resize(photofile=puppy)
    print wrapped.__dict__
    # we'll pass in a guid.  in your code this would be the id in your database
    saved= rFactory.resize(photofile=puppy,s3_save=True,s3_save_original=True,guid='123',s3_logger=s3Logger)
    print saved.__dict__


