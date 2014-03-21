import os
from setuptools import setup

def get_docs():
    result = []
    in_docs = False
    f = open(os.path.join(os.path.dirname(__file__), 'imagehelper/__init__.py'))
    try:
        for line in f:
            if in_docs:
                if line.lstrip().startswith(':copyright:'):
                    break
                result.append(line[4:].rstrip())
            elif line.strip() == 'r"""':
                in_docs = True
    finally:
        f.close()
    return '\n'.join(result)

setup(
    name='imagehelper',
    author='Jonathan Vanasco',
    author_email='jonathan@findmeon.com',
    version='0.1.0.rc9',
    url='http://github.com/jvanasco/imagehelper',
    packages=['imagehelper'],
    description='simple utilites for image resizing and uploading and stuff like that',
    long_description=get_docs(),
    zip_safe=False,
    test_suite='tests',
    classifiers=[
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python',
        "Intended Audience :: Developers",
        "Topic :: Multimedia :: Graphics :: Graphics Conversion",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Development Status :: 4 - Beta",
    ]
)
