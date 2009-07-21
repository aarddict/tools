==========
Aard Tools
==========

.. module:: aardtools
   :platform: Unix
   :synopsis: create and manipulate aard files (.aar)
.. moduleauthor:: Jeremy Mortis
.. moduleauthor:: Igor Tkach

Aard Dictionary uses dictionaries in it's own 
:doc:`binary format <aardformat>` designed for fast word lookups and high
compression. `aardtools` is a collection of tools to produce
:doc:`Aard files <aardformat>` (``.aar``).

Installation
============

.. note::
   Examples below use ``apt-get`` on Ubuntu Linux. Consult your
   distibution's packaging system to find corresponding package names
   and commands to install them. 

Prerequisits
------------

Your system must be able to compile C and C++ programs::

  sudo apt-get install build-essential

You will also need to have Python headers and setuptools_ installed::

  sudo apt-get install python-dev python-setuptools  
 
If you would like to get source code repository you will need
Mercurial_. `aardtools` rely on Python interfaces to several C
libraries:
  
- `International Components for Unicode`_
- libxml2 and libxslt

which must be installed beforehand::

  sudo apt-get install libicu38 libicu-dev
  sudo apt-get install libxml2 libxml2-dev 
  sudo apt-get install libxslt1.1 libxslt-dev 

.. _Mercurial: http://selenic.com/mercurial
.. _setuptools: http://peak.telecommunity.com/DevCenter/setuptools
.. _International Components for Unicode: http://icu-project.org/

Installation
------------

Download aardtools source code::

  wget http://www.bitbucket.org/itkach/aardtools/get/tip.bz2

or 

::

  hg clone http://www.bitbucket.org/itkach/aardtools

Assuming source code code is in `aardtools` directory::

  cd aardtools
  sudo python setup.py install   

Usage
=====
Entry point for `aardtools` is ``aardc`` command - Aard Dictionary compiler. It
requires two arguments: input file type and input file name. Three supported
input types are 

xdxf 
    Dictionaries in XDXF_ format (only `XDXF-visual`_ is supported).

wiki
    Wikipedia articles and templates :abbr:`CDB (Constant Database)`
    built with :command:`mw-buildcdb` from Wikipedia XML dump.

aard
    Dictionaries in aar format. This is useful for updating dictionary metadata
    and changing the way it is split into volumes. Multiple input files can
    be combined into one single or multi volume fictionary.

.. _XDXF: http://xdxf.sourceforge.net/
.. _XDXF-visual: http://xdxf.revdanica.com/drafts/visual/latest/XDXF-draft-028.txt

Synopsis::

  aardc [options] (wiki|xdxf|aard) FILE [FILE2 [FILE3 ...]]

.. note::
   Only `aard` input type allows multiple files.

Compiling Wiki XML Dump
-----------------------

Get a Wiki dump to compile, for example::

  wget http://download.wikimedia.org/simplewiki/20081227/simplewiki-20081227-pages-articles.xml.bz2

Build mwlib article database::

  mw-buildcdb --input  simplewiki-20081227-pages-articles.xml.bz2 --output simplewiki-20081227-pages-articles.cdb

Original dump is not needed after this, it may be deleted or moved to
free up disk space. Compile aar dictionary from the article database::

 aardc wiki simplewiki-20081227-pages-articles.cdb

Compiler infers from the input file name that Wikipedia language
is "simple" and that version is 20081227. These need to be specified
explicitely through command line options if cdb directory name doesn't
follow the pattern of the xml dump file names. Compiler also
looks for files with license and copyright notice texts and dictionary
metadata, first in the language of the wiki and then in
English. English versions of these files are included. 

.. note::
   Make sure :file:`{mwlibdir}/mwlib/siteinfo` directory contains
   file :file:`siteinfo-{lang}.json` for language of wiki to be
   compiled. If it doesn't - run
   :samp:`{mwlibdir}/mwlib/siteinfo/fetch_siteinfo.py {lang}`.

Compiling XDXF Dictionaries
---------------------------

Get a XDXF dictionary, for example::

  wget http://downloads.sourceforge.net/xdxf/comn_dictd04_wn.tar.bz2 

Compile aar dictionary:: 
 
  aardc xdxf comn_dictd04_wn.tar.bz2

Compiling Aard Dictionaries
---------------------------
.aar dictionaries themselves can be used as input for aardc. This is useful
when dictionary's metadata need to be updated or dictionary needs to be split
up into several smaller volumes. For example, to split large dictionary
`dict.aar` into volumes with maximum size of 10 Mb run:: 

  aardc aard dict.aar -o dict-split.aar -s 10m

If `dict.aar` is, say, 15 Mb this will produce two files: 10 Mb `dict-split.1_of_2.aar`
and 5Mb `dict-split.2_of_2.aar`. 

To update dictionary metadata::

  aardc aard dict.aar -o dict2.aar --metadata dict.ini


Release Notes
=============

0.7.4
-----

- Improved Wiki redirect parsing: case insensitive, recognize
  site-specific redirect magic word aliases

- Improved statisics, logging and progress display

- Improved stability and memory usage

- Better guess wiki language and version from input file name


0.7.3
-----

- Compile wiki directly from CDB (original wiki xml dump is no longer
  needed after generating CDB)

- Infer wiki language and version from input file name if it follows
  the same pattern as wiki xml dump file names

- Include a copy of GNU Free Documentation License, wiki copyright
  notice text and general description, write this into
  dictionary metadata by default

- Improve memory usage (`issue #4`_)

.. _issue #4: http://bitbucket.org/itkach/aardtools/issue/4




