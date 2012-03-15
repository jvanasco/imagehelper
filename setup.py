import os
from setuptools import setup

def get_docs():
    result = []
    in_docs = False
    f = open(os.path.join(os.path.dirname(__file__), 'imagehelper.py'))
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
    version='0.0.1',
    url='http://github.com/jvanasco/imagehelper',
    py_modules=['imagehelper'],
    description='simple utilites for image resizing and uploading and stuff like that',
    long_description=get_docs(),
    zip_safe=False,
    test_suite='tests',
    classifiers=[
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python',
        "Intended Audience :: Developers",
    ]
)
