from imagehelper import utils
from six import string_types


def check_archive_original(resizerResultset, archive_original=None):
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

    if archive_original is False:
        return False

    elif archive_original is None:
        if resizerResultset.original:
            return True
        return False

    elif archive_original is True:
        if not resizerResultset.original:
            raise ValueError("""Missing resizerResultset.original for
                explicit archiving""")
        return True


def derive_format(size, resizerResultset, instructions, ):
    """derives the format for a size. this function is needed because
    introspection is necessary when the format will be inherited from the
    original file

    args:
        `size` - string
        `resizerResultset` -
        `instructions` - schema dictionary

    """
    _format = instructions['format']
    if _format.lower() in ('auto', 'original', ):
        # if we used a FakeResultSet to generate the filenames, then the resized will be a string of the suffix
        if not isinstance(resizerResultset.resized[size], string_types):
            _format = resizerResultset.resized[size].format
        else:
            _format = resizerResultset.resized[size]
    return _format


def size_to_filename(guid, size, resizerResultset, filename_template_default, instructions):
    """generates the target_filename for a size.

    args:
        `size` - string
        `resizerResultset` -
        `filename_template_default` - string template
        `instructions` - schema dictionary
    """

    # calc vars for filename templating
    filename_template = filename_template_default
    suffix = size
    if 'filename_template' in instructions:
        filename_template = instructions['filename_template']
    if 'suffix' in instructions:
        suffix = instructions['suffix']

    # use a helper to get the format
    # if we used a FakeResultSet to generate the size_to_filename...
    # ... then the resized will be a string of the suffix
    _format = derive_format(size, resizerResultset, instructions)

    # generate the filename
    target_filename = filename_template % {
        'guid': guid,
        'suffix': suffix,
        'format': utils.PIL_type_to_standardized(_format)
    }
    return target_filename
