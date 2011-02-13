import sys
from setuptools import setup, find_packages

import aardtools

install_requires = ['aarddict >= 0.9.0',
                    'PyICU >= 0.8.1',
                    'mwlib == 0.12.13']

if sys.version_info < (2, 6):
    install_requires += ['simplejson', 'multiprocessing']

setup(
    name = aardtools.__name__,
    version = aardtools.__version__,
    packages = find_packages(),
    entry_points = {
        'console_scripts': ['aardcompile = aardtools.compiler:main',
                            'aardc = aardtools.compiler:main',
                            'aard-siteinfo = aardtools.fetchsiteinfo:main',
                            ]
    },
    install_requires = install_requires,
    package_data={'aardtools': ['licenses/*.txt']},    
    author = "Igor Tkach",
    author_email = "itkach@aarddict.org",
    description =  '''Tools to create dictionaries in aarddict format.''',
    license = "GPL 3",
    keywords = ['aarddict', 'aardtools', 'wiki', 'wikipedia',
                'xdxf', 'dict', 'dictionary', 'maemo'],
    url = "http://aarddict.org",
    classifiers=[
                 'Development Status :: 3 - Alpha',
                 'Operating System :: OS Independent',
                 'Programming Language :: Python',
                 'License :: OSI Approved :: GNU General Public License (GPL)',
                 'Topic :: Utilities',
                 'Environment :: Console'
    ]
)

