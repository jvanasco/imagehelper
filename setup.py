import os
import re
from setuptools import setup, find_packages

# store version in the init.py
with open(
    os.path.join(os.path.dirname(__file__), "imagehelper", "__init__.py")
) as v_file:
    VERSION = re.compile(r".*__VERSION__ = \"(.*?)\"", re.S).match(v_file.read()).group(1)


requires = ["certifi", "envoy", "six", "Pillow"]


setup(
    name="imagehelper",
    author="Jonathan Vanasco",
    author_email="jonathan@findmeon.com",
    version=VERSION,
    url="http://github.com/jvanasco/imagehelper",
    packages=find_packages(exclude=("tests",)),
    description="simple utilites for image resizing and uploading and stuff like that",
    long_description="""The `imagehelper` package offers a simple interface for image resizing, optimizing and uploading. Core image resizing operations are handled by the `Pillow` (PIL) package; S3 uploading is handled by `boto`, and there are hooks for optimizing the images with the commandline tools: `advpng`,  `gifsicle`, `jpegtran`, `jpegoptim`, `optipng` and `pngcrush.`""",
    zip_safe=False,
    test_suite="tests",
    classifiers=[
        "License :: OSI Approved :: BSD License",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 3",
        "Intended Audience :: Developers",
        "Topic :: Multimedia :: Graphics :: Graphics Conversion",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    tests_require=requires,
    install_requires=requires,
)
