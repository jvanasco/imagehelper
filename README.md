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

	# config object for IMAGE_SIZES
	resizerConfig = imagehelper.resizer.ResizerConfig( resizesSchema=IMAGE_SIZES )

	# config object for S3
	s3Config= imagehelper.s3.S3Config(
		key_public = AWS_KEY_PUBLIC,
		key_private = AWS_KEY_SECRET,
		bucket_public_name = AWS_BUCKET_PUBLIC,
		bucket_archive_name = AWS_BUCKET_SECRET,
	)

	# build a factory; you'd probably stash this in your app.
	rFactory= imagehelper.resizer.ResizerFactory( resizerConfig=resizerConfig )
	uploader = imagehelper.s3.S3Uploader( s3Config=s3Config , resizerConfig=rConfig , s3Logger=s3Logger )

	# resize !
	resizedImages = rFactory.resize( imagefile=get_imagefile() )

	# upload the resized items
	uploaded = uploader.s3_save( resizedImages , guid="123" )

	# want to delete them?
	deleted = uploader.s3_delete( uploaded )

Behind the scenes, imagehelper does all the math and uploading.


## Resizing Options

* `fit-within`
> Resizes item to fit within the bounding box , on both height and width.   This resulting image will be the size of the bounding box or smaller.

* `fit-within:crop-to`
> resizes the item along whichever axis ensures the bounding box is 100% full, then crops.  This resulting image will be the size of the bounding box.

* `fit-within:ensure-width`
> resizes item to fit within the bounding box, scaling height to ensure 100% width.  This resulting image will be the size of the bounding box.

* `fit-within:ensure-height`
> resizes item to fit within the bounding box, scaling width to ensure 100% height. This resulting image will be the size of the bounding box.

* `smallest:ensure-minimum`
> resizes the item to cover the bounding box on both axis.  one dimension may be larger than the bounding box.

* `exact:no-resize`
> don't scale! raises an error if a scale must be made. this is a  convenience for just saving/re-encoding files. i.e. 100x100 must receive an image that is 100x100

* `exact:proportion`
> tries to scale the image to an exact size.  raises an error if it can't.  Usually this is used to resample a 1:1 image, however this might be used to drop an image to a specific proportion. i.e. 300x400 can scale to 30x40, 300x400 but not 30x50








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


## Transactional Support

If you upload something via `imagehelper.s3.S3Uploader().s3_upload()` , the task is considered to be "all or nothing".

The actual uploading occurs within a try/except block , and a failure will "roll back" and delete everything that has been successfully uploaded.

If you want to integrate with something like the Zope `transaction` package, `imagehelper.s3.S3Uploader().s3_delete()` is a public function that expects as input the output of the `s3_upload` function -- a `dict` of `tuples` where the `keys` are resize names (from the schema) and the `values` are the `( filename, bucket )`.

You can also define a custom subclass of `imagehelper.s3.S3Logger` that supports the following methods:

* `log_upload`( `self`, `bucket_name`=None, `key`=None , `filesize`=None )
* `log_delete`( `self`, `bucket_name`=None, `key`=None )

Every successful 'action' is sent to the logger.  A valid transaction to upload 5 sizes will have 5 calls to `log_upload`, an invalid transaction will have a `log_delete` call for every `log_upload`.

This was designed for a variety of use cases:

* log activity to a file or non-transactional database connection , you get some efficient bookkeeping of s3 activity and can audit those files to ensure there is no orphan data in your s3 buckts.
* log activity to StatsD or another metrics app to show how much activity goes on


## License

The code is licensed under the BSD license.

The sample image is licensed under the Creative Commons Attribution-NonCommercial-NoDerivs 3.0 Unported (CC BY-NC-ND 3.0) http://creativecommons.org/licenses/by-nc-nd/3.0/







TODO:
    TESTS!
