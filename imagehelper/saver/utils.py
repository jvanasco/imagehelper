

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
