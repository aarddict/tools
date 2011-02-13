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
compression. `Aard Tools` is a collection of tools to produce
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

You will also need to have Python headers::

  sudo apt-get install python-dev

It is highly recommended to install and run `Aard Tools` inside
`virtualenv`_::

  sudo apt-get install python-virtualenv

`Aard Tools` rely on Python interfaces to 
`International Components for Unicode`_, which must be installed
beforehand::

  sudo apt-get install libicu38 libicu-dev
 
If you would like to get source code repository you will need
Git_::

  sudo apt-get install git

.. _virtualenv: http://pypi.python.org/pypi/virtualenv
.. _Git: http://git-scm.com/
.. _setuptools: http://peak.telecommunity.com/DevCenter/setuptools
.. _International Components for Unicode: http://icu-project.org/

When compiling Wikipedia into dictionary with HTML articles `Aard
Tools` renders mathematical formulas using several tools: :command:`latex`,
:command:`blahtexml`, :command:`texvc` and :command:`dvipng`. 

Install :command:`latex`::

  sudo apt-get install texlive-latex-base

Install :command:`blahtexml` following instructions at
http://gva.noekeon.org/blahtexml/

Install :command:`texvc` (it is part of MediaWiki distribution)::

  sudo apt-get install mediawiki-math

Install :command:`dvipng`::

  sudo apt-get install dvipng

:command:`texvc` is what Wikipedia uses to render math and it's most compatible
with the TeX markup flavour used in Wikipedia articles. However, png
images produced by texvc are not transparent and don't look very
good. :command:`blahtexml` has a :command:`texvc` compatibility mode, produces better
looking images, but is more strict about TeX syntax, so it fails on
quite a few equations. So first thing article converter tries is using
:command:`latex` and :command:`dvipng` directly, with some additional LaTeX command
definitions for :command:`texvc` compatibility (borrowed from
:command:`blahtexml`). This produces best looking images and works on most
equations, but not all of them. When it fails, it falls back to
:command:`blahtexml`, and then finally :command:`texvc`. If all fails (for example
neither tools is installed) article ends up with raw math markup.

.. note::
   This applies to HTML article format (:term:`aar-HTML`), which is what aardtools 0.8.0
   uses for Wikipedia by default. Articles in older JSON format (:term:`aar-JSON`) do not
   support math rendering. 

.. warning::
   aarddict 0.7.x can't render :term:`aar-HTML` articles, will show raw HTML. 

Installation
------------

Create Python virtual environment::

  virtualenv env-aard

Activate it::

  env-aard/bin/activate
  source env-aard/bin/activate

and install pip_::

  easy_install pip

.. note::

   Recent versions of virtualenv already come with pip_
   installed. Make sure it's up to date::

     pip install --upgrade pip

Install `Aard Tools`::

  pip install aardtools

or, if you would like to install from the source code repository at
GitHub:: 

  pip install -e git+git://github.com/aarddict/tools.git#egg=aardtools

.. _pip: http://pypi.python.org/pypi/pip

Usage
=====
Entry point for `Aard Tools` is ``aardc`` command - Aard Dictionary compiler. It
requires two arguments: input file type and input file name. Input
file type is the name of Python module that actually reads input files and
performs article conversion. `Aard Tools` "out of the box" comes with
support for the following input types: 

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

  aardc (wiki|xdxf|aard) FILE [FILE2 [FILE3 ...]] [options]

.. note::
   Only `aard` input type allows multiple files.

Compiling Wiki XML Dump
-----------------------

Get a Wiki dump to compile, for example::

  wget http://download.wikimedia.org/simplewiki/20101026/simplewiki-20101026-pages-articles.xml.bz2

Get Mediawiki site information::

  aard-siteinfo simple.wikipedia.org > simple.json

Build mwlib article database::

  mw-buildcdb --input simplewiki-20101026-pages-articles.xml.bz2 --output simplewiki-20101026-pages-articles.cdb

Original dump is not needed after this, it may be deleted or moved to
free up disk space. Compile aar dictionary from the article database::

 aardc wiki simplewiki-20101026-pages-articles.cdb --siteinfo simple.json

Compiler infers from the input file name that Wikipedia language
is "simple" and that version is 20101026. These need to be specified
explicitely through command line options if cdb directory name doesn't
follow the pattern of the xml dump file names. 

If siteinfo's general section specifies one of the two licences used
for `Wikimedia Foundation`_ projects - `Creative Commons
Attribution-Share Alike 3.0 Unported`_ or `GNU Free Documentation
License 1.2`_ - license text will be included into dictionary's
metadata. You can also specify explicitly files containing license
text and copyright notice with ``--license`` and ``--copyright``
options. Use ``--metadata`` option to specify file containing
additional dictionary meta data, such as description.

.. _Wikimedia Foundation: http://wikimediafoundation.org
.. _Creative Commons Attribution-Share Alike 3.0 Unported: http://creativecommons.org/licenses/by-sa/3.0/legalcode
.. _GNU Free Documentation License 1.2: http://www.gnu.org/licenses/fdl-1.2.html


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


Compiling WordNet_
------------------

.. versionadded: 0.8.2   

Get complete WordNet_ distribution::

  wget http://wordnetcode.princeton.edu/3.0/WordNet-3.0.tar.bz2

Unpack it::

  tar -xvf WordNet-3.0.tar.bz2

and compile::

  aard wordnet WordNet-3.0	

.. _WordNet: http://wordnet.princeton.edu/


Reporting Issues
================

Please submit issue reports and enhancement requests to `Aard
Tools issue tracker`_.

.. _Aard Tools issue tracker: http://github.com/aarddict/tools/issues


Release Notes
=============

0.8.3
-----

- Add ``--rtl`` compilation option for wiki converter - adds `dir`
  attribute with value `rtl` to article's enclosing element.

- Fix aard converter (was broken after refactoring in aarddict 0.9.0)


0.8.2
-----

- Add WordNet_ convertor


0.8.1
-----

- Exclude more boxes, exclude sister and inter project links

- Add ``--article-count`` option - compile specified number of articles,
  not counting redirects

- Change article format for xdxf from json to html

- Add option ``--skip-article-title`` for xdxf to not add article title
  at the beginning of article (some dicitonaries already have it) 

- Remove support for article :term:`aar-JSON` article format 

- Add command to fetch siteinfo, require that siteinfo file is
  explicitely specified with ``--siteinfo`` option

- Don't load default license, copyright and metadata files, don't
  provide any defaults when loading specified meta data

- Don't include any language links languages by default

- Add known wiki licenses

- Better version guessing from file name

- Updated mwlib dependency to 0.12.13

- Make compiler work with aarddict 0.9.0

0.8.0
-----

- Use json module from standard lib if using Python 2.6

- Update mwlib dependency to 0.12.10

- Add option to convert Wikipedia articles to HTML instead of JSON

- Render math in Wikipedia articles (when converting to HTML)

- Properly handle multiple occurences of named references in Wikipedia
  articles (when converting to HTML)

- Properly handle multiple reference lists in Wikipedia
  articles (when converting to HTML)

- Use upwords arrow character instead of ^ for footnote back
  references 

- Add list of language link languages to metadata

- Generate smaller dictionaries when compiling Wikipedia by excluding
  more metadata, navigation and image related elements 

0.7.6
-----

- Add Wikipedia language link support (include article titles from
  language links into index for languages specified with ``--lang-links``
  option)

- Rework title sorting implementation to speed up title sorting step

- Use simple text file with index instead of shelve for temporary
  article storage to reduce disk space requirements

- Change default max file size to 2 :superscript:`31` - 1 instead of
  2 :superscript:`32` - 1 

0.7.5
-----

- Include license, doc and wiki files in source distribution generated
  by setuptools_

- Write Wikipedia siteinfo to dictionary metadata

- Exclude elements with classes `navbar` and `plainlinksneverexpand`,
  this get's rid of talk-view-edit links in wiki articles

- Discard generic tag attributes when parsing wiki since they are not
  used

- Updated Wikipedia copyright and license information to reflect
  Wikipedia's switch to Common Attribution license

- Removed dependency on lxml_

- Moved converter specific functions to converter modules, this
  makes it possible to implement new converters without changing
  compiler.py

- Parse XDXF's ``nu`` and ``opt`` tags

.. _lxml: http://codespeak.net/lxml/

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

- Improve memory usage (:tools-issue:`4`)




