#### IMPORTANT Note:

This package is in the process of being largely rewritten....

## About

`imagehelper` is a fork of some image helping routines that were built at FindMeOn a while back.

`imagehelper` allows you to define a schema for resizing images as a simple `dict`, and will then easily resize them.

`imagehelper` also supports uploading the resized images - and an archival version - onto amazon's s3.

`imagehelper` will try to use `Pillow` but fall back on `PIL` if that is unavailable.  it will try to import `boto` for communicating with s3.  If you don't want to use s3, no worries.

The package was originally aimed at thumbnails, but it works for all resizing needs that are aimed at downsampling images.

This is a barebones package that has NO FRAMEWORK DEPENDENCIES - which is a good thing.  You define a dict, it does the rest.

I could only find a single tool for resizing thumbnails on PyPi that did not require a framework, and that's really annoying.

This is still in Beta.


## Why ?

Imagine that you have a site that allows for user generated uploads , or you want to make video stills...

You can create a schema of image sizes...

	IMAGE_SIZES = {
		'thumb': {
			'width': 32,
			'height': 32,
			'save_quality': 50,
			'suffix': 't1',
			'format':'JPEG',
			'constraint-method': 'fit-within',
			'filename_template': '%(guid)s-120x120.%(format)s',
		},
		'og:image': {
			'width': 200,
			'height': 200,
			'save_quality': 50,
			'suffix': 'og',
			'format':'JPEG',
			'constraint-method': 'ensure-minimum',
			'filename_template': '%(guid)s-og.%(format)s',
		},
	}

And easily upload them :

	# new resizer config
	rConfig = newResizerConfig()

	# build a factory
	rFactory= imagehelper.resizer.ResizerFactory( resizer_config=rConfig )

	# resize !
	resizedImages = rFactory.resize( imagefile=get_imagefile() )

	# new s3 config & logger
	s3Config = newS3Config()
	s3Logger = CustomS3Logger()

	# upload the resized items
	uploader = imagehelper.s3.S3Uploader( s3_config=s3Config , resizer_config=rConfig , s3_logger=s3Logger )
	uploaded = uploader.s3_save( resizedImages , guid="123" )

	# want to delete them?
	deleted = uploader.s3_delete( uploaded )

Behind the scenes, imagehelper does all the math and uploading.


## Resizing Options

* `fit-within` peg to the smallest proportion so the entire image fits
* `fit-within:crop-to` peg so the smallest dimension fills the canvas, then crop the rest.
* `fit-within:ensure-width` resize so the width fills the canvas, and the height is scaled to match
* `fit-within:ensure-height` resize so the height fills the canvas, and the width is scaled to match
* `smallest:ensure-minimum` useful for things like og:image where you want at least a 200px image ( dupe of fit-within ? )
* `exact:proportion` scale to exact size. raises an error if this is not possible.  ( ie 300x400 can scale to 30x40, but not 30x50 )
* `exact:no-resize` don't scale! raises an error if a scale must be made. this is a convenience.







## Usage...

Check out the demo.py module - and include some amazon s3 credentials in an `aws.cfg` file.  a template is provided.

1. Create a dict of "photo resizes" describing your schema.

* keys prepended with `save_` are passed on to PIL during the call to `save` (the prefix is removed)
* you can decide what type of resizing you want.  sometimes you want to crop, other times you want to fit within a box, other times you want to ensure a height or width.  this makes your designers happy.

2. create an array of image_resizes_selected -- the keys in the above schema you want to resize.

3. you can pass these arguments into the routines themselves, or generate a ResizeConfig object an a resize factory that you stash into your app settings.

4. If you're saving to S3, create an S3 config object to store your info.  note that you can specify a public and private bucket.

* resized thumbnails are saved to the public bucket
*  the original item is optionally saved to the archive, which is not viewable to the public.  this is so you can do different sizing schemes in the future.

5. You can define your own S3 logger, a class that provides two methods:

*     log_upload( bucket_name , key )
*     log_delete( bucket_name , key )

This will allow you to log what is uploaded into amazon aws on your side.  This is hugely helpful , because amazon uploads are not transaction safe to your application logic.  there are some built-in precautions for this... but it's best to play things safely.


items are currented saved to amazon s3 as such:

public:

	%(guid)s-%(suffix)s.%(format)s

	guid- you must supply a guid for the file
	suffix- this is set in the resize schema
	format- this is dictated by the PIL format type

archive:
	%(guid)s.%(format)s
	guid- you must supply a guid for the file
	format- this is dictated by the original format type PIL found

here's an example photo_resize schema

    'jpeg_thumbnail-120': {
        'width': 120,
        'height': 120,
        'save_quality': 50,
        'suffix': 't120',
        'format':'JPEG',
        'constraint-method': 'fit-within',
        's3_bucket_public': 'my-test',
        'filename_template': '%(guid)s-%(suffix)s.%(format)s',
        's3_headers': { 'x-amz-acl' : 'public-read' }
    },


this would create a file on amazon s3 with a GUID you supply like 123123123g :

	/my-test/123123123-t120.jpg
	_bucket_/_guid_-_suffix_._format_




## License

The code is licensed under the BSD license.

The sample image is licensed under the Creative Commons Attribution-NonCommercial-NoDerivs 3.0 Unported (CC BY-NC-ND 3.0) http://creativecommons.org/licenses/by-nc-nd/3.0/







TODO:
    TESTS!
