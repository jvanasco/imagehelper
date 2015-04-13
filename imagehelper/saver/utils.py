

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


def derive_format(instructions, resizerResultset, size):
    _format = instructions['format']
    if _format.lower() in ('auto', 'original', ):
        # if we used a FakeResultSet to generate the filenames, then the resized will be a string of the suffix
        if not isinstance(resizerResultset.resized[size], (str, unicode)):
            _format = resizerResultset.resized[size].format
        else:
            _format = resizerResultset.resized[size]
    return _format
