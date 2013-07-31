import logging
log = logging.getLogger(__name__)

import os


class ImageErrorCodes(object):
    """Consolidating codes and error messages"""
    INVALID_FILETYPE = 1
    INVALID_OTHER = 2
    NO_IMAGE = 3
    MISSING_FILE = 4
    UNSUPPORTED_IMAGE_CLASS = 5     ## Must be cgi.FieldStorage or file
    INVALID_REBUILD = 6
    MISSING_FILENAME_METHOD = 7



_PIL_type_to_content_type= {
    'gif': 'image/gif',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'pdf':'application/pdf',
    'png': 'image/png',
}

_PIL_type_to_standardized= {
    'gif': 'gif',
    'jpg': 'jpg',
    'jpeg': 'jpg',
    'pdf': 'pdf',
    'png': 'png',
}


def PIL_type_to_content_type( ctype ):
    ctype = ctype.lower()
    if ctype in _PIL_type_to_content_type:
        return _PIL_type_to_content_type[ ctype ]
    raise ValueError('invalid ctype')

def PIL_type_to_standardized( ctype ):
    ctype = ctype.lower()
    if ctype in _PIL_type_to_standardized:
        return _PIL_type_to_standardized[ ctype ]
    raise ValueError('invalid ctype')



def filesize( fileobj ):
    """what's the size of the object?"""
    fileobj.seek(0,os.SEEK_END)
    sized = fileobj.tell()
    fileobj.seek(0)
