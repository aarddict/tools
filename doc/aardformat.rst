=============
Aard Format
=============

Container Format
================
Aard Dictionary container format is a binary file format that combines
dictionary metadata, lookup index and compressed article data.

Aard files have the following layout: header, metadata, index 1, index 2, articles

Header
------
Aard files start with a fixed size header described by the following
specification::

  HEADER_SPEC = (('signature',                '>4s'),
		 ('sha1sum',                  '>40s'),
		 ('version',                  '>H'), 
		 ('uuid',                     '>16s'), 
		 ('volume',                   '>H'), 
		 ('of',                       '>H'), 
		 ('meta_length',              '>L'),
		 ('index_count',              '>L'), 
		 ('article_offset',           '>L'), 
		 ('index1_item_format',       '>4s'), 
		 ('key_length_format',        '>2s'),
		 ('article_length_format',    '>2s'),
		 )  

signature
  signature string 'aard' identifying file as Aard Dictionary file

sha1sum
  sha1 sum of dictionary file content following signature and sha1 bytes

version
  Aard format version, a number, currently must be 1

uuid
  dictionary unique identifier shared by all volumes of the same dictionary

volume
  volume number of this this file

of
  total number of volumes for the dictionary

meta_length
  length of metadata compressed string

index_count
  number of words in the dictionary

article_offset
  article offset 

index1_item_format
  either `>LL` or `>LQ` (if maximum volume file size is set to a value bigger
  then 2^32 - 1) - :mod:`struct` format for key pointer and article
  pointer. 

key_length_format
  `>H` - key length format in index2_item

article_length_format
  `>L` - article length format                              

Metadata
--------
Metadata is a dictionary stored as a JSON-encoded string. Aard Dictionary
viewer uses the following metadata keys:

article_count
  number of unique articles in the dictionary (in all volumes combined)

index_language
  dictionary's "from" language (two or thre letter ISO code)

article_language
  dictionary's "from" language (two or thre letter ISO code)

title
  dictionary title

version
  dictionary version

description
  dictionary desription

copyright
  copyright notice

license
  full license text

source
  description of the source from which dicionary data originated

Index 1
-------
Index 1 is a sequence of fixed-size items containing two values: pointer to
Index 2 item and pointer to article item.

Index 2
-------
Index 2 is a sequence of variable-length items containing two values: length of
dictionary key text and key text itself.

Articles
--------
Articles is a sequence of variable length items containing two values: length
of article text and article text itself.

.. seealso:: 
   
   Module :mod:`struct`
     `Documentation <http://docs.python.org/library/struct.html>`_ for the
     :mod:`struct` module 

Article Formats
===============
From container format perspective article is just a string that is stored
either as is or compressed with gzip or bz2 whichever takes less space. Thus
articles in Aard files may be in any format that is can be represented as
string, for example plain text or HTML. Article format name is specified by
metadata key ``article_format``. 

Currently Aard  Dictionary viewer can only display JSON-encoded articles in the
format desribed below (``article_format`` is set to `json`). 

Article is represented by a tuple consisting of article ``text``, ``tags`` and
optional attributes dictionary (so article tuple length may be either 2 or 3). 
``text`` is UTF8 encoded string. ``tags`` is a sequence of tag tuples. Each tag
tuple is a tuple of values for tag name, start position, end position and
optional attribute dictionary (so each tag tuple has length of either 3 or
4). This data structure is converted to string via JSON serialization. 

