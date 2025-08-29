import os
import re
import sys
from setuptools import find_packages
from setuptools import setup

HERE = os.path.abspath(os.path.dirname(__file__))

# store version in the init.py
with open(os.path.join(HERE, "src", "imagehelper", "__init__.py")) as v_file:
    VERSION = (
        re.compile(r".*__VERSION__ = \"(.*?)\"", re.S).match(v_file.read()).group(1)
    )

description = "Simple utilites for image resizing and uploading and stuff like that."
long_description = """The `imagehelper` package offers a simple interface for image resizing, optimizing and uploading. Core image resizing operations are handled by the `Pillow` (PIL) package; S3 uploading is handled by `boto3`, and there are hooks for optimizing the images with the commandline tools: `advpng`,  `gifsicle`, `jpegtran`, `jpegoptim`, `optipng` and `pngcrush.`"""
with open(os.path.join(HERE, "README.md")) as fp:
    long_description = fp.read()

requires = [
    "envoy",
    "Pillow",
    "typing_extensions",
]
if sys.version_info >= (3, 13):
    requires.append("legacy-cgi")

tests_require = [
    "boto3",
    # "botocore",  # part of boto3; listed to upgrade better
    # "certifi",
    "mypy-boto3-s3",
    "pytest",
    "requests",
    "types-Pillow",
    "types-requests",
    # "urllib3",  # used by botocore; listed to upgrade better
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
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Intended Audience :: Developers",
        "Topic :: Multimedia :: Graphics :: Graphics Conversion",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    py_modules=["imagehelper"],
    license="BSD",
    packages=find_packages(
        where="src",
    ),
    package_dir={"": "src"},
    package_data={"imagehelper": ["py.typed"]},
    include_package_data=True,
    zip_safe=False,
    install_requires=requires,
    tests_require=tests_require,
    extras_require={
        "testing": testing_extras,
    },
    test_suite="tests",
)
