# stlib
from typing import Optional

# local
from .. import utils
from ..image_wrapper import ResizerInstructions
from ..resizer import ResizerResultset

# ==============================================================================


def check_archive_original(
    resizerResultset: ResizerResultset,
    archive_original: Optional[bool] = None,
) -> bool:
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

    # elif archive_original is True:
    else:
        if not resizerResultset.original:
            raise ValueError(
                """Missing resizerResultset.original for
                explicit archiving"""
            )
        return True


def derive_resized_format(
    size: str,
    resizerResultset: ResizerResultset,
    instructions: ResizerInstructions,
) -> str:
    """derives the format for a size. this function is needed because
    introspection is necessary when the format will be inherited from the
    original file

    args:
        `size` - string
        `resizerResultset` -
        `instructions` - schema dictionary

    ONLY USED BY `size_to_filename`

    SEE ALSO: imagehelper.utils.derive_format

    """
    intended_format: str = instructions["format"]
    if intended_format.upper() in ("AUTO", "ORIGINAL"):
        assert resizerResultset.original.format
        intended_format = utils.derive_format(
            intended_format, resizerResultset.original.format
        )
    return intended_format


def size_to_filename(
    guid: str,
    size: str,
    resizerResultset: ResizerResultset,
    filename_template_default: str,
    instructions: ResizerInstructions,
) -> str:
    """generates the target_filename for a size.

    args:
        `size` - string
        `resizerResultset` -
        `filename_template_default` - string template
        `instructions` - schema dictionary
    """

    # calc vars for filename templating
    filename_template = filename_template_default
    if "filename_template" in instructions:
        filename_template = instructions["filename_template"]

    suffix = size
    if "suffix" in instructions:
        # overwrite the "size" id with "suffix"
        suffix = instructions["suffix"]

    # use a helper to get the format
    # if we used a FakeResultSet to generate the size_to_filename...
    # ... then the resized will be a string of the suffix
    _format = derive_resized_format(size, resizerResultset, instructions)

    # generate the filename
    target_filename = filename_template % {
        "guid": guid,
        "suffix": suffix,
        "format": utils.PIL_type_to_standardized(_format),
    }
    return target_filename
