=========
aardtools
=========

.. module:: aardtools
   :platform: Unix
   :synopsis: create and manipulate aard files (.aar)
.. moduleauthor:: Jeremy Mortis
.. moduleauthor:: Igor Tkach

Aard Dictionary uses dictionaries in it's own binary format - :ref:`aard <aard-format>` - designed for fast word 
lookups and high compression. `aardtools` is a collection of tools to produce
`aard` (``.aar``)files .

Installation
============

Prerequisits
------------
You need to have Python setuptools_ installed. If you would like to get source code 
repository you will need Mercurial_. `aardtools` rely on Python interfaces to several 
C libraries which must be installed beforehand:
  
- `International Components for Unicode`_
- libxml2 and libxslt

For example, on Ubuntu::

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
    Dictionaries in XDXF_ format (only XDXF-visual is supported).

wiki
    Wikipedia XML dump.

aard
    Dictionaries in aar format. This is useful for updating dictionary metadata
    and changing the way it is split into volumes.

    .. note::

       Currently only one input file can be specified, so it is only possible to
       split a large dictionary into several volumes. 

.. _XDXF: http://xdxf.sourceforge.net/

Synopsis::

  aardc [options] (wiki|xdxf|aard) FILE

Compiling Wiki XML Dump
-----------------------

Get a Wiki dump to compile, for example::

  wget http://download.wikimedia.org/simplewiki/20081227/simplewiki-20081227-pages-articles.xml.bz2

Build mwlib article database::

  mw-buildcdb --input  simplewiki-20081227-pages-articles.xml.bz2 --output simplewiki-20081227-pages-articles.cdb

Compile aar dictionary::

 aardc wiki simplewiki-20081227-pages-articles.xml.bz2 -t simplewiki-20081227-pages-articles.cdb 

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






