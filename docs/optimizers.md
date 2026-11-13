# Image optimizers

ImageHelper can run command-line optimizers after Pillow encodes an image. To
enable this during resizing, set `optimize_original` or `optimize_resized` on
`ResizerConfig`. To optimize an existing `BasicImage`, call `image.optimize()`.

## Install the tools

macOS with MacPorts

```sh
sudo port install advancecomp gifsicle libjpeg-turbo jpegoptim optipng pngcrush
export PATH="/opt/local/bin:$PATH"
```

macOS with Homebrew

```sh
brew install advancecomp gifsicle jpeg-turbo jpegoptim optipng pngcrush
export PATH="$(brew --prefix jpeg-turbo)/bin:$PATH"
```

Ubuntu

```sh
sudo apt-get update
sudo apt-get install advancecomp gifsicle libjpeg-turbo-progs jpegoptim optipng pngcrush
```

Install any subset you need. ImageHelper checks executable availability on first
use and skips missing tools. A service must have the appropriate PATH in its own
environment.

## What each optimizer does

| Format | Tool | Default behavior |
| --- | --- | --- |
| JPEG | `jpegtran` | Optimizes entropy coding and writes a progressive JPEG. Copies JPEG markers. |
| JPEG | `jpegoptim` | Optimizes without setting a new quality level and strips metadata, including EXIF and ICC profiles. |
| GIF | `gifsicle` | Optimizes at level 3. Keeps the input interlace setting by default. |
| PNG | `pngcrush` | Tries lossless reductions and strips removable ancillary chunks. |
| PNG | `optipng` | Recompresses at level 3 and writes a non-interlaced PNG. |
| PNG | `advpng` | Recompresses PNG data at level 4. This is the highest compression setting and can be slow. |

Within each format, the tools run in the order shown. Each tool starts from the
last valid output. ImageHelper skips a stage if it fails, times out after 60
seconds, or produces undecodable output or output with a different format,
dimensions, or frame count. It retains the input when every stage fails.
Metadata removal can affect color management and EXIF-based orientation.

## Configure detection and GIF interlacing

Set process-wide options at startup before running optimization:

```python
from imagehelper.image_wrapper import OPTIMIZE_SUPPORT, autodetect_support

OPTIMIZE_SUPPORT["jpegtran"]["binary"] = "/opt/local/bin/jpegtran"
OPTIMIZE_SUPPORT["jpegoptim"]["use"] = False
OPTIMIZE_SUPPORT["gifsicle"]["options"]["interlace"] = True
autodetect_support()
```

Use `False` to write non-interlaced GIFs and `None` to preserve the input setting.
Disabling `jpegoptim` avoids its metadata stripping step. After a call to
`optimize()`, `image.optimizations` lists attempted tools and whether their
output was accepted. `image.optimization_savings` is the original byte count
minus the final byte count. A negative value means the output grew.

## Run the tests and benchmark

From the repository root, using an environment with ImageHelper and its testing
extra installed:

```sh
IMAGEHELPER_REQUIRE_OPTIMIZERS=1 python -m pytest -q tests/test_optimizers.py
IMAGEHELPER_BENCHMARK=1 python -m pytest -qs tests/test_optimizers.py -k benchmark
```

The benchmark reports the median elapsed time of five runs, the original and
final encoded byte counts, and percentage size change for each installed tool
and the default chains. Time includes subprocess startup, temporary files, and
output validation. Compare runs on the same machine with the same tool versions.
