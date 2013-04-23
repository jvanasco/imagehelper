This is a fork of some image helping routines that we built at FindMeOn a while back.

The package allows you to configure a schema for resizing images, and easily resize them.  It also supports uploading the images onto amazon s3.

This is aimed at thumbnails, but it works for all resizing needs that are aimed at downsampling images.

I released this, because this has NO FRAMEWORK DEPENDENCIES - which is a good thing.

I could only find a single tool for resizing thumbnails on PyPi that did not require a framework, and that's really annoying.  

This is still in Alpha as it is made to be more 'universal' ( it was originally coded for Pylons , and now is targeted --  but does not require -- Pyramid )

----

The code is licensed under the BSD license.

The sample image is licensed under the Creative Commons Attribution-NonCommercial-NoDerivs 3.0 Unported (CC BY-NC-ND 3.0) http://creativecommons.org/licenses/by-nc-nd/3.0/

----

Usage...

Check out the demo.py module - and include some amazon s3 credentials.

1. Create a dict of "photo resizes" describing your schema.  
    keys prepended with saved_ are passed on to PIL
    you can decide what type of resizing you want.  sometimes you want to crop, other times you want to fit within a box, other times you want to ensure a height or width.  this makes your designers happy.
    
2. create an array of photo_resizes_selected -- the keys in the above schema you want to resize.

3. you can pass these arguments into the routines themselves, or generate a ResizeConfig object an a resize factory that you stash into your app settings.  
    
4. If you're saving to S3, create an S3 config object to store your info.  note that you can specify a public and private bucket.
    resized thumbnails are saved to the public bucket
    the original item is optionally saved to the archive, which is not viewably to the public.  this is so you can do different sizing schemes in the future.
    
5. You can create an S3 logger, a class that provides two methods:
    log_upload( bucket_name , key )
    log_delete( bucket_name , key )
    
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




TODO:
    TESTS!