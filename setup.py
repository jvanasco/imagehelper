import os
import re
from setuptools import setup, find_packages

# store version in the init.py
with open(
    os.path.join(os.path.dirname(__file__), "imagehelper", "__init__.py")
) as v_file:
    VERSION = (
        re.compile(r".*__VERSION__ = \"(.*?)\"", re.S).match(v_file.read()).group(1)
    )

description = ("simple utilites for image resizing and uploading and stuff like that",)
long_description = (
    """The `imagehelper` package offers a simple interface for image resizing, optimizing and uploading. Core image resizing operations are handled by the `Pillow` (PIL) package; S3 uploading is handled by `boto`, and there are hooks for optimizing the images with the commandline tools: `advpng`,  `gifsicle`, `jpegtran`, `jpegoptim`, `optipng` and `pngcrush.`""",
)
try:
    here = os.path.abspath(os.path.dirname(__file__))
    long_description = open(os.path.join(here, "README.md")).read()
except:
    pass

requires = [
    "certifi",
    "envoy",
    "six",
    "Pillow",
]
tests_require = [
    "boto",
    "requests",
    "pytest",
]
testing_extras = tests_require + []

setup(
    name="imagehelper",
    version=VERSION,
    url="http://github.com/jvanasco/imagehelper",
    author="Jonathan Vanasco",
    author_email="jonathan@findmeon.com",
    description=description,
    long_description=long_description,
    long_description_content_type="text/markdown",
    classifiers=[
        "License :: OSI Approved :: BSD License",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 3",
        "Intended Audience :: Developers",
        "Topic :: Multimedia :: Graphics :: Graphics Conversion",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    py_modules=["imagehelper"],
    license="BSD",
    packages=find_packages(exclude=("tests",)),
    zip_safe=False,
    install_requires=requires,
    tests_require=tests_require,
    extras_require={
        "testing": testing_extras,
    },
    test_suite="tests",
)
