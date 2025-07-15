# stdlib
from typing import Any
from typing import Dict
from typing import List
from typing import Tuple
from typing import TYPE_CHECKING
from typing import Union

# pypi
from typing_extensions import NotRequired
from typing_extensions import TypedDict

if TYPE_CHECKING:
    from .image_wrapper import BasicImage

# ==============================================================================


# !!!: `constraint-method="passthrough:no-resize"` has no width/height
ResizerInstructions = TypedDict(
    "ResizerInstructions",
    {
        # required
        "width": Union[int, None],
        "height": Union[int, None],
        "constraint-method": str,
        "format": str,
        # optional as in we have defaults
        "filename_template": NotRequired[str],
        "save_quality": NotRequired[int],
        "suffix": NotRequired[str],
        # optional below
        "allow_animated": NotRequired[bool],
        # optional - Pillow
        # https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html#jpeg-saving
        # https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html#png-saving
        "save_optimize": NotRequired[Any],
        "save_progressive": NotRequired[Any],
        "save_transparency": NotRequired[Any],
        "save_bits": NotRequired[Any],
        "save_dictionary": NotRequired[Any],
        # optional extensions
        "boto3_ExtraArgs": NotRequired[Any],
    },
)

ResizesSchema = Dict[str, ResizerInstructions]


TYPE_files_mapping = Dict[str, Tuple[str, str]]
TYPE_resizes = Dict[str, "BasicImage"]
TYPE_selected_resizes = Union[List[str], Tuple[str]]
