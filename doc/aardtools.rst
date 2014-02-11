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


Requirements
============

- Python 2.7
- UNIX-like OS.
- Compiling large Mediawiki dumps such as English or German Wikipedia
  requires **64-bit** multicore machine.


Installation
============

.. note::
   Instructions below are for Ubuntu Linux 12.10. Consult your
   distibution's packaging system to find corresponding package names
   and commands to install them.

Prerequisites
-------------

Your system must be able to compile C and C++ programs::

  sudo apt-get install build-essential

Your system must be able to compiled Python C extensions::

  sudo apt-get install python-dev

`Aard Tools` will be installed in a  `virtualenv`_::

  sudo apt-get install python-virtualenv

`Aard Tools` rely on Python interfaces to
`International Components for Unicode`_, which must be installed
beforehand::

  sudo apt-get install libicu-dev

Install other non-Python dependencies::

  sudo apt-get install libevent-dev libxml2-dev libxslt1-dev

Install Git_::

  sudo apt-get install git

.. _virtualenv: http://pypi.python.org/pypi/virtualenv
.. _Git: http://git-scm.com/
.. _setuptools: http://peak.telecommunity.com/DevCenter/setuptools
.. _International Components for Unicode: http://icu-project.org/

`Aard Tools` renders mathematical formulas using several tools: :command:`latex`,
:command:`blahtexml`, :command:`texvc` and :command:`dvipng`.

Install :command:`latex`::

  sudo apt-get install texlive-latex-base

Install `blahtex`_::

  sudo apt-get install blahtexml

.. _blahtex: http://gva.noekeon.org/blahtexml/

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


Installation
------------

Create Python virtual environment::

  virtualenv env-aard

Activate it::

  source env-aard/bin/activate

Install `Aard Tools`::

  pip install -e git+git://github.com/aarddict/tools.git#egg=aardtools


Usage
=====
Entry point for `Aard Tools` is ``aardc`` command - Aard Dictionary compiler. It
requires two arguments: input file type and input file name. Input
file type is the name of Python module that actually reads input files and
performs article conversion. `Aard Tools` "out of the box" comes with
support for the following input types:

xdxf
    Dictionaries in XDXF_ format (only `XDXF-visual`_ is supported).

mwcouch
    Wikipedia articles stored in CouchDB (as returned by `MediaWiki
    API`_'s `parse`)

wiki
    Wikipedia articles and templates :abbr:`CDB (Constant Database)`
    built with :command:`mw-buildcdb` from Wikipedia XML dump.

aard
    Dictionaries in aar format. This is useful for updating dictionary metadata
    and changing the way it is split into volumes. Multiple input files can
    be combined into one single or multi volume dictionary.

wordnet
   WordNet_

.. _CouchDB: http://couchdb.apache.org
.. _MediaWiki API: https://www.mediawiki.org/wiki/API
.. _XDXF: http://xdxf.sourceforge.net/
.. _XDXF-visual: http://xdxf.revdanica.com/drafts/visual/latest/XDXF-draft-028.txt

Synopsis::

  usage: aardc [-h] [--version] [-o OUTPUT_FILE] [-s MAX_FILE_SIZE] [-d] [-q]
               [--work-dir WORK_DIR] [--show-legend] [--log-file LOG_FILE]
               [--metadata METADATA] [--license LICENSE] [--copyright COPYRIGHT]
               [--dict-ver DICT_VER] [--dict-update DICT_UPDATE]
               {wiki,xdxf,wordnet,aard,mwcouch,dummy} ...

  optional arguments:
    -h, --help            show this help message and exit
    --version             show program's version number and exit
    -o OUTPUT_FILE, --output-file OUTPUT_FILE
                          Output file name. By default is the same as input file
                          base name with .aar extension
    -s MAX_FILE_SIZE, --max-file-size MAX_FILE_SIZE
                          Maximum file size in bytes, kilobytes(K), megabytes(M)
                          or gigabytes(G). Default: 2147483647 bytes
    -d, --debug           Turn on debugging messages
    -q, --quite           Print minimal information about compilation progress
    --work-dir WORK_DIR   Directory for temporary file created during
                          compilatiod. Default: .
    --show-legend         Show progress legend
    --log-file LOG_FILE   Log file name. By default derived from output file
                          name by adding .log extension
    --metadata METADATA   INI containing dictionary metadata in [metadata]
                          section
    --license LICENSE     Name of a UTF-8 encoded text file containing license
                          text
    --copyright COPYRIGHT
                          Name of a UTF-8 encoded text file containing copyright
                          notice
    --dict-ver DICT_VER   Version of the compiled dictionary
    --dict-update DICT_UPDATE
                          Update number for the compiled dictionary. Default: 1

  converters:
    Available article source types

    {wiki,xdxf,wordnet,aard,mwcouch,dummy}


Compiling MediaWiki CouchDB Dump
--------------------------------

Get MediaWiki CouchDB using `mwscrape.py`_ (if downloading pre-made
CouchDB_ database be sure to also download siteinfo database and/or run
`mwscrape.py`_ to fetch or update it).

Run

::

  aardc mwcouch -h

for usage details and complete list of options.

For example, command to compile a dictionary from a database named
``ru-m-wiktionary-org`` on a local CouchDB server may look like this::

  aardc mwcouch http://localhost:5984/ru-m-wiktionary-org --filter-file ~/aardtools/mwcouch/filters/wiktionary.txt

Optional content filter file may be specified to clean up articles of
unnecessary elements and to reduce resulting dictionary size.  Content
filter file for ``mwcouch`` converter is a text file with one CSS
selector per line. Individual selectors may also be specified as
command line argument.  Each selector is applied to article HTML and
matching elements are removed. See BeautifulSoup_ documentation for
details on supported selectors. Sample content filters for a typical
Note that no content filters are applied by default.

.. _BeautifulSoup: http://www.crummy.com/software/BeautifulSoup/bs4/doc/
.. _mwscrape.py: https://github.com/itkach/mwscrape


Compiling Wiki XML Dump
-----------------------

.. note::

   Since early 2013 Wikipedia sites are actively using `Lua
   scripting`_ instead of traditional MediaWiki templates. Such
   content is not rendered by mwlib_, library wiki converter uses to
   parse MediaWiki markup. Use ``mwcouch`` converter instead, as
   described above.

.. _mwlib: http://pediapress.com/code/
.. _Lua scripting: https://www.mediawiki.org/wiki/Lua_scripting

Get a Wiki dump to compile, for example::

  wget http://download.wikimedia.org/simplewiki/20101026/simplewiki-20101026-pages-articles.xml.bz2

Get Mediawiki site information::

  aard-siteinfo simple.wikipedia.org > simple.json

Build mwlib article database::

  mw-buildcdb --input simplewiki-20130203-pages-articles.xml.bz2 --output simplewiki-20130203.cdb

Original dump is not needed after this, it may be deleted or moved to
free up disk space.

Parsing certain content elements is locale specific. Make sure your
system has approparite locale available. For example, if compiling
Polish Wikipedia::

  sudo locale-gen pl

Compile small sample dictionary from the article database::

 aardc wiki simplewiki-20130203.cdb simplewiki.json --article-count 1000 --filter enwiki

Verify that resulting dictionary has good metadata (description,
license, source url), that "View Online" action works and article
formatting is formatting. Content filters may need to be created or
modified to clean up resulting articles of unwanted navigational
links, article messages, empty sections etc. In the example above we
indicate that we would like to use built-in filter set for English
Wikipedia.

.. seealso:: `Content Filters`_
.. seealso:: `Language Links`_

Compiler infers from the input file name that Wikipedia language
is "simple" and that version is 20130203. These need to be specified
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

Content Filters
~~~~~~~~~~~~~~~

.. versionadded: 0.9.0

Content filters are defined in YAML_, as a dictionary with the
following keys:

EXCLUDE_PAGES
  List of regular expressions matching Mediawiki template
  names. Excluding templates improves compilation performance since
  their content is completely excluded from processing.

  .. note::
     Entries containing ``:`` character must be quoted

EXCLUDE_CLASSES
  List of HTML class names to be excluded. Article HTML elements having one of
  these classes will be excluded from final output.

EXCLUDE_IDS
  List of HTML element ids to excluded. Article HTML elements having one of
  these ids will be excluded from final output.

TEXT_REPLACE
  List of dictionaries with `re` and `sub` keys defining text
  substitutions. Text substitutions are performed on the resulting
  article HTML text.
  Matching expressions will be replaced with optional substition text
  If no substition text is provided, matching patterns will be removed

Here's an example of content filter file:

.. code-block:: yaml

   EXCLUDE_PAGES:
     - "Template:Only in print"
     # Don't process navigation boxes
     - "Template:Navbar"
     - "Template:Navbox"
     - "Template:Navboxes"
     - "Template:Side box"
     - "Template:Sidebar with collapsible lists"
     # No need for audio
     - "Template:Audio"
     - "Template:Spoken Wikipedia"
     # Bulky and unnecessary tables
     - "Template:Latin alphabet navbox"
     - "Template:Greek Alphabet"
     # Exclude any stub templates, match case-insensitive
     - "(?i).*-stub"

   EXCLUDE_CLASSES:
     - collapsible
     - maptable
     - printonly

   EXCLUDE_IDS:
     - interProject

   TEXT_REPLACE:
     - re  : "&lt;(\\w+) (class=[^>]*?)&gt;"
       sub : "<\\1 \\2>"

     # Remove empty sections
     # Used in articles like encyclopaedia
     - re  : "<div><h.>[\\w\\s]*</h.>(<p>\\s*</p>)*</div>"


Excluding content by template name is the most effective approach,
however sometimes it is more convenient and concise to exclude content
by HTML class or id. Text replacement is useful for things like fixing
broken output of some templates and getting rid of empty sections. Run
with ``--debug`` to have converted article html logged - text
replacement regular expressions should be tested against it.

Content filters are specified with ``--filters`` command line
option, as a path to the filters file, or a name of one of filter
files bundled with aardtools. For example, filters defined for English
Wikipedia also work well for Simple English Wikipedia, so to compile
simplewiki we can run

::

 aardc wiki simplewiki-20130203.cdb simplewiki.json --filter enwiki


.. seealso:: `Documentation <http://docs.python.org/2/library/re.html>`_ for the :mod:`re` module


.. _YAML: http://www.yaml.org/

Language Links
~~~~~~~~~~~~~~

Many Wikipedia articles include language links - links to the
same article in a different language. Optionally, article titles in
other languages can be added to lookup index. This is specified with
``--lang-links`` command line option. For example::

  aardc wiki enwiki-20130128.cdb enwiki.json --lang-links de fr

In resulting dictionary articles can be found by their German and
French title, in addition to English. Note that adding language links
slightly increases resulting dictionary size.


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

  aardc wordnet WordNet-3.0

.. _WordNet: http://wordnet.princeton.edu/


Reporting Issues
================

Please submit issue reports and enhancement requests to `Aard
Tools issue tracker`_.

.. _Aard Tools issue tracker: http://github.com/aarddict/tools/issues
