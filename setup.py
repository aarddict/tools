from setuptools import setup, find_packages
import sys, os

setup(
    name = "aardtools",
    version = '0.7.0',
    packages = find_packages(),
    entry_points = {
        'console_scripts': ['aardcompile = aardtools.compiler:main',
                            'aardc = aardtools.compiler:main']
    },

    install_requires = [ 'aarddict >= 0.7.0',
                         'PyICU >= 0.8.1', 
                         'mwlib == 0.8.5', 
                         'lxml >= 2.0', 
                         'simplejson',
                         'multiprocessing'],

    author = "Igor Tkach",
    author_email = "itkach@gmail.com",
    description =  '''Tools to create dictionaries in aarddict format.''',
    license = "GPL 3",
    keywords = ['aarddict', 'aardtools', 'dict', 'dictionary', 'maemo'],
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

