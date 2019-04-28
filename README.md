#### IMPORTANT Note:

This package was in the process of being largely rewritten... It really needs to be rewritten, but is production safe

## About

`imagehelper` is a fork of some image helping routines that were built for FindMeOn.com around 2005.

`imagehelper` allows you to define a schema for resizing images as a simple `dict`, and will then easily resize them.

`imagehelper` also supports uploading the resized images - and an archival version - onto amazon's s3.

`imagehelper` requires `Pillow`. Earlier versions relied on `PIL` or supported both. This is an old package.

it will try to import `boto` for communicating with s3.  If you don't want to use s3, no worries.

The package was originally aimed at thumbnails, but it works for all resizing needs that are aimed at downsampling images.

If you have optimization applications like `gifsicle`, `pngcrush` and `jpegtran` installed in your environment, you can 'optimize' the output (and archive) files.

This is a barebones package that has NO FRAMEWORK DEPENDENCIES - which is a good thing.  You define a dict, it does the rest.

This package also tries to avoid writing to disk whenever possible, tempfiles (spooled) are avoided unless an external program is called. this tries to pipe everything through file-like in-memory objects

I could only find a single tool for resizing thumbnails on PyPi that did not require a framework, and that's really annoying.

The package is a bit awkard to use for a single task, but it was designed for repetitive tasks - as in a web application.

A typical usage is illustrated in the sections below.  Also check the `demo.py` file to see how neat it can be

This is still in Beta, but has been production safe.

It supports Python2.7 and Python3.  A lot of things could be done better and should be done better, but this works and is relatively fast.


## Why ?

Imagine that you have a site that allows for user generated uploads, or you want to make video stills...

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

And easily upload them:

	# create some configs in your app

	# config object for IMAGE_SIZES
	resizerConfig = imagehelper.resizer.ResizerConfig(
		resizesSchema=IMAGE_SIZES,
		optimize_original=True,
    	optimize_resized=True,
    )

	# config object for S3
	saverConfig= imagehelper.saver.s3.SaverConfig(
		key_public = AWS_KEY_PUBLIC,
		key_private = AWS_KEY_SECRET,
		bucket_public_name = AWS_BUCKET_PUBLIC,
		bucket_archive_name = AWS_BUCKET_SECRET,
	)

	# create some factories.
	# factories are unnecessary. they just generate the workhorse objects for you
	# they're very useful for cutting down code
	# build one, then stash in your app

	USE_FACTORY = True
	if USE_FACTORY:
		rFactory = imagehelper.resizer.ResizerFactory(resizerConfig=resizerConfig)
		s3Factory = imagehelper.saver.s3.s3ManagerFactory(saverConfig=saverConfig, resizerConfig=rConfig, saverLogger=saverLogger)

		resizer = rFactory.resizer()
		s3Manager = s3Factory.saver_manager()

	else:
		resizer = imagehelper.resizer.Resizer(resizerConfig=resizerConfig)
		s3Manager = imagehelper.saver.s3.s3Manager(saverConfig=saverConfig, resizerConfig=resizerConfig, saverLogger=saverLogger)

	# resize !
	resizedImages = resizer.resize(imagefile=get_imagefile())

	# upload the resized items
	uploaded_files = s3Manager.files_save(resizedImages, guid="123")

	# want to delete them?
	deleted = s3Manager.files_delete(uploaded_files)

Behind the scenes, imagehelper does all the math and uploading.


## Resizing Options

* `fit-within`
> Resizes item to fit within the bounding box, on both height and width.   This resulting image will be the size of the bounding box or smaller.

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

Check out the demo.py module - it offers a narrative demo of how to use the package. Be sure to include some amazon s3 credentials in an `aws.cfg` file.  a template is provided.

imagehelper is NOT designed for one-off resizing needs.  it's designed for a use in applications where you're repeatedly doing the same resizing.

The general program flow is this:

1. Create `Configuration` objects to hold instructions
2. Create `Factory` objects to hold the `Configuration` objects.
3. Obtain a `Worker` object from the `Factory` to do the actual work (resizing or uploading)

You should typically create Configuration and Factory objects during application startup, and create/destroy a work for each request or event.

Here's a more in depth description

1. Create a dict of "photo resizes" describing your schema.

* keys prepended with `save_` are passed on to PIL during the call to `save` (the prefix is removed)
* you can decide what type of resizing you want.  sometimes you want to crop, other times you want to fit within a box, other times you want to ensure a height or width.  this makes your designers happy.

2. create an array of image_resizes_selected -- the keys in the above schema you want to resize.

3. you can pass these arguments into the routines themselves, or generate a ResizeConfig object an a resize factory that you stash into your app settings.

4. If you're saving to S3, create an S3 config object to store your info.  note that you can specify a public and private bucket.

* resized thumbnails are saved to the public bucket
*  the original item is optionally saved to the archive, which is not viewable to the public.  this is so you can do different sizing schemes in the future.

5. You can define your own S3 logger, a class that provides two methods:

    class SaverLogger(object):
		def log_save(self, bucket_name=None, key=None, file_size=None, file_md5=None):
			pass
		def log_delete(self, bucket_name=None, key=None):
			pass

This will allow you to log what is uploaded into amazon aws on your side.  This is hugely helpful, because amazon uploads are not transaction safe to your application logic.  there are some built-in precautions for this... but it's best to play things safely.


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
        's3_headers': { 'x-amz-acl': 'public-read' }
    },


this would create a file on amazon s3 with a GUID you supply like 123123123g:

	/my-test/123123123-t120.jpg
	_bucket_/_guid_-_suffix_._format_

string templates may be used to affect how this is saved. read the source for more info.

## Transactional Support

If you upload something via `imagehelper.saver.s3.S3Uploader().s3_upload()`, the task is considered to be "all or nothing".

The actual uploading occurs within a try/except block, and a failure will "roll back" and delete everything that has been successfully uploaded.

If you want to integrate with something like the Zope `transaction` package, `imagehelper.saver.s3.S3Uploader().files_delete()` is a public function that expects as input the output of the `s3_upload` function -- a `dict` of `tuples` where the `keys` are resize names (from the schema) and the `values` are the `(filename, bucket)`.

You can also define a custom subclass of `imagehelper.saver.s3.SaverLogger` that supports the following methods:

* `log_save`(`self`, `bucket_name`=None, `key`=None, `file_size`=None, `file_md5`=None)
* `log_delete`(`self`, `bucket_name`=None, `key`=None)

Every successful 'action' is sent to the logger.  A valid transaction to upload 5 sizes will have 5 calls to `log_save`, an invalid transaction will have a `log_delete` call for every successful upload.

This was designed for a variety of use cases:

* log activity to a file or non-transactional database connection, you get some efficient bookkeeping of s3 activity and can audit those files to ensure there is no orphan data in your s3 buckts.
* log activity to StatsD or another metrics app to show how much activity goes on


## FAQ - package components

* `errors` - custom exceptions
* `image_wrapper` - actual image reading/writing, resize operations
* `resizer` - manage resizing operations
* `s3` - manage s3 communication
* `utils` - miscellaneous utility fucntions


## FAQ - deleting existing files ?

if you don't have a current mapping of the files to delete in s3 but you do have the archive filename and a guid, you can easily generate what they would be based off a resizerConfig/schema and the archived filename.

    ## fake the sizes that would be generated off a resize
    resizer = imagehelper.resizer.Resizer(
    	resizerConfig=resizerConfig,
		optimize_original=True,
		optimize_resized=True,
	)
    fakedResizedImages = resizer.fake_resultset(original_filename = archive_filename)

    ## generate the filenames
	deleter = imagehelper.saver.s3.SaverManager(saverConfig=saverConfig, resizerConfig=resizerConfig)
	targetFilenames = build.generate_filenames(fakedResizedImages, guid)

the `original_filename` is needed in fake_resultset, because a resultset tracks the original file and it's type.  as of the 0.1.0 branch, only the extension of the filename is utilized.


## FAQ - validate uploaded image ?

this is simple.

1. create a dumb resizer factory

    nullResizerFactory = imagehelper.resizer.ResizerFactory()

2. validate it

	try:
		resizer = nullResizerFactory.resizer(
			imagefile = uploaded_image_file,
		)
	except imagehelper.errors.ImageError_Parsing, e:
		raise ValueError('Invalid Filetype')

	# grab the original file for advanced ops
	resizerImage = resizer.get_original()
	if resizerImage.file_size > MAX_FILESIZE_PHOTO_UPLOAD:
		raise ValueError('Too Big!')


passing an imagefile to `ResizerFactory.resizer` or `Resizer.__init__` will register the file with the resizer.  This action creates an `image_wrapper.ImageWrapper` object from the file, which contains the original file and a PIL/Pillow object.  If PIL/Pillow can not read the file, an error will be raised.


## FAQ - what sort of file types are supported ?

All the reading and resizing of image formats happens in PIL/Pillow.

imagehelper tries to support most common file objects

`imagehelper.image_wrapper.ImageWrapper` our core class for reading files, supports reading the following file types

* `file (native python object, i.e. `types.FileType`)
* `cgi.FieldStorage`
* `StringIO.StringIO`, `cStringIO.InputType`, `cStringIO.OutputType`

we try to be kind and rewind.  we call seek(0) on the underlying file when approprite, but sometimes forget.

the resize operations accepts the following file kwargs:

* `imagefile` -- one of the above file objects
* `imageWrapper` -- an instance of `imagehelper.image_wrapper.ImageWrapper`
* `file_b64` -- a base64 encoded file datastream. this will decoded into a cStringIO object for operations.


## FAQ - using celery ?

celery message brokers require serialized data.

in order to pass the task to celery, you will need to serialize/deserialize the data.  imagehelper provides convenience functionality for this

    nullResizerFactory = imagehelper.resizer.ResizerFactory()
	resizer = nullResizerFactory.resizer(
		imagefile = uploaded_file,
	)

	# grab the original file for advanced ops
	resizerImage = resizer.get_original()

	# serialize the image
	instructions = {
		'image_md5': resizerImage.file_md5,
		'image_b64': resizerImage.file_b64,
		'image_format': resizerImage.format,
	}

	# send to celery
	deferred_task = celery_tasks.do_something.apply_async((id, instructions,))


	# in celery...
	@task
	def do_something(id, instructions):
		## resize the images
		resizer = resizerFactory.resizer(
			file_b64 = instructions['image_b64'],
		)
		resizedImages = resizer.resize()


## How are optimizations handled?

Image optimizations are handled by piping the image through external programs.  The idea (and settings) were borrowed from the mac app ImageOptim https://github.com/pornel/ImageOptim / https://imageoptim.com/

The default image Optimizations are LOSSLESS

Fine-grained control of image optimization strategies is achieved on a package level basis.  In the future this could be handled within configuration objects.  This strategy was chosen for 2 reasons:

1. The config objects were getting complex
2. Choosing an image optimization level is more of a "machine" concern than a "program" concern.

Not everyone has every program installed on their machines

`imagehelper` will attempt to autodetect what is available on the first invocation of `.optimize`

if you are on a forking server, you can do this before the fork and save yourself a tiny bit of cpu cycles. yay.

	import imagehelper
	imagehelper.image_wrapper.autodetect_support()

The `autodetect_support` routing will set 

	imagehelper.image_wrapper[ program ]['available']

if you want to enable/disable them manuall, just edit

	imagehelper.image_wrapper[ program ]['use']

you can also set a custom binary

	imagehelper.image_wrapper[ program ]['binary']

autodetection is handled by invoking each program's help command to see if it is installed


### JPEG

jpegs are optimized in a two-stage process.

	jpegtran is used to do an initial optimization and ensure a progressive jpeg.  all the jpeg markers are preserved.
	jpegoptim is used on the output of the above, in this stage all jpeg markers are removed.

The exact arguments are:

	"""jpegtran -copy all -optimize -progressive -outfile %s %s""" % (fileOutput.name, fileInput.name)
	"""jpegoptim --strip-all -q %s""" % (fileOutput.name, )

### GIF

Gifsicle is given the following params
    -O3
    --no-comments
    --no-names
    --same-delay
    --same-loopcount
    --no-warnings

The 03 level can be affected by changing the package level variable to a new integer (1-3)

	imagehelper.image_wrapper.OPTIMIZE_GIFSICLE_LEVEL = 3


### PNG

The package will try to use multiple png operators in sequence.

You can disable any png operator by changing the package level variable to False

	OPTIMIZE_PNGCRUSH_USE = True
	OPTIMIZE_OPTIPNG_USE = True
	OPTIMIZE_ADVPNG_USE = True


#### pngcrush

	pngcrush -rem alla -nofilecheck -bail -blacken -reduce -cc

#### optipng

	optipng -i0 -o3

The optipng level can be set by setting the package level variable to a new integer (1-3)

	OPTIMIZE_OPTIPNG_LEVEL = 3  # 6 would be best

#### advpng

	advpng -4 -z

The advpng level can be set by setting the package level variable to a new integer (1-4)

	OPTIMIZE_ADVPNG_LEVEL = 4  # 4 is max




## ToDo

See the Todo file



## License

The code is licensed under the BSD license.

The sample image is licensed under the Creative Commons Attribution-NonCommercial-NoDerivs 3.0 Unported (CC BY-NC-ND 3.0) http://creativecommons.org/licenses/by-nc-nd/3.0/
