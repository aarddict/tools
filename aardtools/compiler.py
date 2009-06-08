#!/usr/bin/python

# This file is part of Aard Dictionary Tools <http://aarddict.org>.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3
# as published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License <http://www.gnu.org/licenses/gpl-3.0.txt>
# for more details.
#
# Copyright (C) 2008-2009  Jeremy Mortis, Igor Tkach


from __future__ import with_statement
import uuid
import logging
import sys
import struct
import os
import tempfile
import shelve
import optparse
import functools
import time
import shutil

from PyICU import Locale, Collator
import simplejson

from sortexternal import SortExternal
from aarddict.dictionary import HEADER_SPEC, spec_len, calcsha1
import aardtools


log = logging.getLogger('compiler')

tojson = functools.partial(simplejson.dumps, ensure_ascii=False)

MAX_FAT32_FILE_SIZE = 2**32-1

KEY_LENGTH_FORMAT = '>H'
ARTICLE_LENGTH_FORMAT = '>L'
INDEX1_ITEM_FORMAT = '>LL'

def make_opt_parser():
    usage = "Usage: %prog [options] (wiki|xdxf|aard) FILE"
    parser = optparse.OptionParser(version="%prog 1.0", usage=usage)
    parser.add_option(
        '-o', '--output-file',
        default='',
        help=
        'Output file name. By default is the same as input '
        'file base name with .aar extension'
        )
    parser.add_option(
        '-s', '--max-file-size',
        default=str(MAX_FAT32_FILE_SIZE),
        help=
        'Maximum file size in megabytes(M) or gigabytes(G). '
        'Default: %default'
        )
    parser.add_option(
        '-t', '--templates',
        default=None,
        help='Template definitions database'
        )
    parser.add_option(
        '-d', '--debug',
        action='store_true',
        default=False,
        help='Turn on debugging messages'
        )
    parser.add_option(
        '-q', '--quite',
        action='store_true',
        default=False,
        help='Print minimal information about compilation progress'
        )
    parser.add_option(
        '--timeout',
        type='float',
        default=2.0,
        help=
        'Skip article if it was not process in the amount of time '
        'specified. Default: %defaults'
        )
    parser.add_option(
        '--processes',
        type='int',
        default=None,
        help=
        'Size of the worker pool (by default equals to the '
        'number of detected CPUs).'
        )
    parser.add_option(
        '--nomp',
        action='store_true',
        default=False,
        help='Disable multiprocessing, useful for debugging.'
        )
    parser.add_option(
        '--metadata',
        default=None,
        help='INI containing dictionary metadata in [metadata] section'
        )
    parser.add_option(
        '--license',
        default=None,
        help='Name of a UTF-8 encoded text file containing license text'
        )
    parser.add_option(
        '--copyright',
        default=None,
        help='Name of a UTF-8 encoded text file containing copyright notice'
        )
    parser.add_option(
        '--work-dir',
        default='.',
        help=
        'Directory for temporary file created during compilatiod. '
        'Default: %default'
        )
    parser.add_option(
        '--start',
        default=0,
        type='int',
        help='Starting article, skip all articles before. Default: %default'
        )

    parser.add_option(
        '--end',
        default=None,
        type='int',
        help='End article, stop processing at this article. Default: %default'
        )

    parser.add_option(
        '--dict-ver',
        help='Version of the compiled dictionary'
        )

    parser.add_option(
        '--dict-update',
        default='1',
        help='Update number for the compiled dictionary. Default: %default'
        )

    parser.add_option(
        '--wiki-lang',
        help='Wikipedia language (like en, de, fr). This may be different from actual language '
        'in which articles are written. For example, the value for Simple English Wikipedia  is "simple" '
        '(although the actual articles language is "en"). This is inferred from input file name '
        'if it follows same naming pattern as Wiki XML dumps and starts with "{lang}wiki". '
        'Default: %default'
        )

    parser.add_option(
        '--mp-chunk-size',
        default=10000,
        type='int',
        help='This value defines maximum number articles to be processed by pool'
        'of worker processes before it is closed and new pool is created. Typically'
        'there should be no need to change the default value.'
        'Default: %default'
        )

    parser.add_option('--log-file',
                       help='Log file name. By default derived from output '
                       'file name by adding .log extension')

    return parser

def utf8(func):
    def f(*args, **kwargs):
        newargs = [arg.encode('utf8') if isinstance(arg, unicode) else arg
                   for arg in args]
        newkwargs = {}
        for key, val in kwargs.iteritems():
            newkwargs[key] = (val.encode('utf8')
                              if isinstance(val, unicode) else val)
        return func(*newargs, **newkwargs)
    f.__doc__ = func.__doc__
    f.__name__ = func.__name__
    f.__dict__.update(func.__dict__)
    return f

class Volume(object):

    class ExceedsMaxSize(Exception): pass

    number = 0

    def __init__(self, header_meta_len, max_file_size, work_dir):
        self.header_meta_len = header_meta_len
        self.max_file_size = max_file_size
        self.index1 = tempfile.NamedTemporaryFile(prefix='index1',
                                                  dir=work_dir)
        log.info('Creating temporary index 1 file %s', self.index1.name)
        self.index2 = tempfile.NamedTemporaryFile(prefix='index2',
                                                  dir=work_dir)
        log.info('Creating temporary index 2 file %s', self.index2.name)
        self.articles =  tempfile.NamedTemporaryFile(prefix='articles',
                                                     dir=work_dir)
        log.info('Creating temporary articles file %s', self.articles.name)
        self.index1Length = 0
        self.index2Length = 0
        self.articles_len = 0
        self.index_count = 0
        Volume.number += 1

    def add(self, index1_unit, index2_unit, article_unit):
        if sum((self.header_meta_len,
                self.index1Length,
                self.index2Length,
                self.articles_len,
                len(index1_unit),
                len(index2_unit),
                len(article_unit)
                )) > self.max_file_size:
            raise Volume.ExceedsMaxSize
        self.index1.write(index1_unit)
        self.index1Length += len(index1_unit)
        self.index2.write(index2_unit)
        self.index2Length += len(index2_unit)
        self.index_count += 1
        self.articles.write(article_unit)
        self.articles_len += len(article_unit)


    def flush(self):
        self.index1.flush()
        self.index2.flush()
        self.articles.flush()

    def totuple(self):
        return (self.index1, self.index1Length, self.index2,
                self.index2Length, self.articles, self.articles_len,
                self.index_count)

import threading
article_add_lock = threading.RLock()

class Stats(object):

    def __init__(self):
        self.total = 0
        self.skipped = 0
        self.failed = 0
        self.empty = 0
        self.timedout = 0
        self.articles = 0
        self.redirects = 0

    def __str__(self):
        return ('total: %d, skipped: %d, failed: %d, '
                'empty: %d, timed out: %d, articles: %d, '
                'redirects: %d' % (self.total, 
                                   self.skipped,
                                   self.failed,
                                   self.empty,
                                   self.timedout,
                                   self.articles,
                                   self.redirects
                                   ))


class Compiler(object):

    def __init__(self, output_file_name, max_file_size, session_dir, metadata=None):
        self.uuid = uuid.uuid4()
        self.output_file_name = output_file_name
        self.max_file_size = max_file_size
        self.index_count = 0
        self.session_dir = session_dir
        self.index_db_fname = os.path.join(self.session_dir, "articles.db")
        self.index_db = shelve.open(self.index_db_fname, 'n')
        self.metadata = metadata if metadata is not None else {}
        self.file_names = []
        self.stats = Stats()
        log.info('Collecting articles')

    @utf8
    def add_metadata(self, key, value):
        if key not in self.metadata:
            self.metadata[key] = value
        else:
            log.warn('Value for metadata key %s is already set, '
                     'new value %s will be ignored',
                     key, value)

    @utf8
    def add_article(self, title, serialized_article, redirect=False):
        with article_add_lock:
            if not title:
                log.warn('Blank title, ignoring article "%s"', serialized_article)
                return

            if not serialized_article:
                self.empty_article(title)
                return

            if self.index_db.has_key(title):
                articles = self.index_db[title]
                log.debug('Adding article for "%s" (already have %d)',
                          title, len(articles))
            else:
                log.debug('Article for "%s"', title)
                articles = []
            articles.append(compress(serialized_article))
            self.index_db[title] = articles
            if not redirect:
                self.stats.articles += 1
            else:
                self.stats.redirects += 1
            print_progress(self.stats)

    @utf8
    def fail_article(self, title):
        self.stats.failed += 1
        print_progress(self.stats)

    @utf8
    def empty_article(self, title):
        self.stats.empty += 1
        print_progress(self.stats)

    @utf8
    def skip_article(self, title):
        self.stats.skipped += 1
        print_progress(self.stats)

    def timedout(self, count=1):
        self.stats.timedout += count
        print_progress(self.stats)

    def total(self, value):
        if self.stats.total is None:
            self.stats.total = value
        else:
            self.stats.total += total

    def compile(self):
        
        self.add_metadata("article_count", self.stats.articles)
        #erase_progress(self.stats.processed)
        sortex = self.sort()
        log.info('Compiling %s', self.output_file_name)
        metadata = compress(tojson(self.metadata))
        header_meta_len = spec_len(HEADER_SPEC) + len(metadata)
        create_volume_func = functools.partial(self.create_volume,
                                               header_meta_len)
        for volume in self.make_volumes(create_volume_func, sortex):
            m = "Creating volume %d" % volume.number
            log.info(m)
            msg(m)
            file_name = self.make_aar(volume)
            self.file_names.append(file_name)
            m = "Wrote volume %d" % volume.number
            log.info(m)
            msg(m)
        sortex.cleanup()
        self.index_db.close()
        self.write_volume_count()
        self.write_sha1sum()
        self.rename_files()

    def sort(self):
        log.info('Sorting')
        msg('Sorting')
        work_dir=os.path.join(self.session_dir, "sort")
        sortex = SortExternal(work_dir=work_dir)
        for title in self.index_db:
            coll_key4_str = (collator4.
                             getCollationKey(title).
                             getByteArray())
            sortex.put(coll_key4_str + "___" + title)
        sortex.sort()
        return sortex

    def create_volume(self, header_meta_len):
        return Volume(header_meta_len, self.max_file_size, self.session_dir)

    def make_volumes(self, create_volume_func, sortex):
        volume = create_volume_func()
        for count, item in enumerate(sortex):
            title = item.split("___", 1)[1]
            serialized_articles = self.index_db[title]
            for serialized_article in serialized_articles:
                index1Unit = struct.pack(INDEX1_ITEM_FORMAT,
                                         volume.index2Length,
                                         volume.articles_len)
                index2Unit = struct.pack(KEY_LENGTH_FORMAT, len(title)) + title
                article_unit = (struct.pack(ARTICLE_LENGTH_FORMAT,
                                           len(serialized_article)) +
                                serialized_article)
                try:
                    volume.add(index1Unit, index2Unit, article_unit)
                except Volume.ExceedsMaxSize:
                    volume.flush()
                    yield volume
                    volume = create_volume_func()
                    index1Unit = struct.pack(INDEX1_ITEM_FORMAT,
                                             volume.index2Length,
                                             volume.articles_len)
                    volume.add(index1Unit, index2Unit, article_unit)
        volume.flush()
        yield volume

    def write_header(self, output_file, meta_length, index1Length,
                     index2Length, index_count, volume):
        article_offset = (spec_len(HEADER_SPEC) + meta_length +
                          index1Length + index2Length)
        values = dict(signature='aard',
                      sha1sum='0'*40,
                      version=1,
                      uuid=self.uuid.bytes,
                      volume=volume,
                      of=0,
                      meta_length=meta_length,
                      index_count=index_count,
                      article_offset=article_offset,
                      index1_item_format=INDEX1_ITEM_FORMAT,
                      key_length_format=KEY_LENGTH_FORMAT,
                      article_length_format=ARTICLE_LENGTH_FORMAT
                      )
        for name, fmt in HEADER_SPEC:
            output_file.write(struct.pack(fmt, values[name]))

    def write_meta(self, output_file, metadata):
        output_file.write(metadata)

    def write_index1(self, output_file, index1):
        log.debug('Writing index 1')
        index1.seek(0)
        count = 0
        while True:
            unit = index1.read(struct.calcsize(INDEX1_ITEM_FORMAT))
            if len(unit) == 0:
                break
            index2ptr, offset = struct.unpack(INDEX1_ITEM_FORMAT, unit)
            unit = struct.pack(INDEX1_ITEM_FORMAT, index2ptr, offset)
            output_file.write(unit)
            count += 1
        log.debug('Wrote %d items to index 1', count)
        index1.close()

    def write_index2(self, output_file, index2):
        log.debug('Writing index 2')
        index2.seek(0)
        count = 0
        while True:
            unitLengthString = index2.read(struct.calcsize(KEY_LENGTH_FORMAT))
            if len(unitLengthString) == 0:
                break
            count += 1
            unitLength, = struct.unpack(KEY_LENGTH_FORMAT, unitLengthString)
            unit = index2.read(unitLength)
            output_file.write(unitLengthString + unit)
        log.debug('Wrote %d items to index 2', count)
        index2.close()

    def write_articles(self, output_file, articles):
        articles.seek(0)
        count = 0
        while True:
            unitLengthString = articles.read(struct.
                                             calcsize(ARTICLE_LENGTH_FORMAT))
            if len(unitLengthString) == 0:
                break
            count += 1
            unitLength, = struct.unpack(ARTICLE_LENGTH_FORMAT,
                                        unitLengthString)
            unit = articles.read(unitLength)
            output_file.write(unitLengthString + unit)
        log.debug('Wrote %d items to articles', count)
        articles.close()

    def write_sha1sum(self):
        for file_name in self.file_names:
            log.info("Calculating checksum for %s", file_name)
            offset = spec_len(HEADER_SPEC[:2])
            sha1sum = calcsha1(file_name, offset)
            log.info("sha1 (first %d bytes skipped): %s", offset, sha1sum)
            output_file = open(file_name, "r+b")
            output_file.seek(spec_len(HEADER_SPEC[:1]))
            output_file.write(sha1sum)
            output_file.close()

    def make_aar(self, volume):
        (index1, index1Length, index2, index2Length, articles,
         articles_len, index_count) = volume.totuple()
        file_name = '%s.%d' % (self.output_file_name, Volume.number)
        output_file = open(file_name, "wb", 8192)
        metadata = compress(tojson(self.metadata))
        self.write_header(output_file, len(metadata), index1Length,
                          index2Length, index_count, Volume.number)
        self.write_meta(output_file, metadata)
        self.write_index1(output_file, index1)
        self.write_index2(output_file, index2)
        self.write_articles(output_file, articles)
        output_file.close()
        log.info("Done with %s", file_name)
        return file_name        

    def write_volume_count(self):
        name, fmt = HEADER_SPEC[5]
        log.info("Writing volume count %d to all volumes as %s",
                 Volume.number, fmt)
        log.debug('Writing' )
        for file_name in self.file_names:
            output_file = open(file_name, "r+b")
            output_file.seek(spec_len(HEADER_SPEC[:5]))
            output_file.write(struct.pack(fmt, Volume.number))
            output_file.close()

    def rename_files(self):
        if len(self.file_names) == 1:
            file_name = self.file_names[0]
            base, ext, vol = file_name.rsplit('.', 2)
            newname = "%s.%s" % (base, ext)
            log.info('Renaming %s ==> %s', file_name, newname)
            msg('Created %s' % bold(newname))
            os.rename(file_name, newname)
        else:
            for file_name in self.file_names:
                base, ext, vol = file_name.rsplit('.', 2)
                newname = "%s.%s_of_%s.%s" % (base,vol,Volume.number,ext)
                log.info('Renaming %s ==> %s', file_name, newname)
                msg('Created %s' % bold(newname))
                os.rename(file_name, newname)

import zlib
import bz2

def _zlib(s):
    return zlib.compress(s)

def _bz2(s):
    return bz2.compress(s)

from collections import defaultdict
compress_counts = defaultdict(int)

def compress(text):
    compressed = text
    cfunc = None
    for func in (_zlib, _bz2):
        c = func(text)
        if len(c) < len(compressed):
            compressed = c
            cfunc = func
    if cfunc:
        compress_counts[cfunc.__name__] += 1
    else:
        compress_counts['none'] += 1
    return compressed

root_locale = Locale('root')
collator4 =  Collator.createInstance(root_locale)
collator4.setStrength(Collator.QUATERNARY)

def compile_wiki(input_file, options, compiler):
    import wiki
    p = wiki.WikiParser(options, compiler)
    p.parse(input_file)

def compile_xdxf(input_file, options, compiler):
    import xdxf
    p = xdxf.XDXFParser(compiler)
    p.parse(input_file)

def compile_aard(input_file, options, compiler):
    import aard
    p = aard.AardParser(compiler)
    p.parse(input_file)

def make_wiki_input(input_file_name):
    return input_file_name

def make_xdxf_input(input_file_name):
    if input_file_name == '-':
        return sys.stdin
    import tarfile
    try:
        tf = tarfile.open(input_file_name)
    except:
        #probably this is not tar archive, open regular file
        return open(input_file_name)
    else:
        for tar in tf:
            if os.path.basename(tar.name) == 'dict.xdxf':
                return tf.extractfile(tar)
    raise IOError("%s doesn't look like a XDXF dictionary" % input_file_name)

def make_aard_input(input_file_name):
    if input_file_name == '-':
        return sys.stdin
    return open(input_file_name)

def wiki_total(inputfile, options):
    import wiki
    return wiki.total(inputfile, options)

known_types = {'wiki': (make_wiki_input, compile_wiki, wiki_total),
               'xdxf': (make_xdxf_input, compile_xdxf, None),
               'aard': (make_aard_input, compile_aard, None)}

def make_output_file_name(input_file, options):
    """
    Return output file name based on input file name.

    >>> from minimock import Mock
    >>> opts = Mock('options')
    >>> opts.output_file = 'abc'
    >>> make_output_file_name('123.tar.bz2', opts)
    'abc'

    >>> opts.output_file = None
    >>> make_output_file_name('123.tar.bz2', opts)
    '123.aar'

    >>> make_output_file_name('-', opts)
    'dictionary.aar'

    """
    if options.output_file:
        output_file = options.output_file
    elif input_file == '-':
        output_file = 'dictionary.aar'
    else:
        output_file = strip_ext(input_file)
        output_file += '.aar'
    return output_file

def strip_ext(fname):
    """
    Return file name with one or two extension stripped
    (depending on extension).

    >>> strip_ext('abc.def.txt')
    'abc.def'
    >>> strip_ext('abc.def.tar.bz2')
    'abc.def'
    >>> strip_ext('abc.def.tar.gz')
    'abc.def'
    >>> strip_ext('abc.def.xml.bz2')
    'abc.def'
    >>> strip_ext('abc.def.xdxf')
    'abc.def'

    """
    output_file = os.path.basename(fname)
    output_file = output_file[:output_file.rfind('.')]
    if (output_file.endswith('.tar') or
        output_file.endswith('.xml') or
        output_file.endswith('.xdxf')):
        output_file = output_file[:output_file.rfind('.')]
    return output_file


def max_file_size(options):
    s = options.max_file_size
    s = s.lower()
    if s.endswith('m'):
        return int(s.strip('m'))*1000000
    elif s.endswith('g'):
        return int(s.strip('g'))*1000000000
    elif s.endswith('k'):
        return int(s.strip('k'))*1000
    elif s.endswith('b'):
        return int(s.strip('b'))
    else:
        return int(s)

ERASE_LINE = '\033[2K'
ERASE_START_OF_LINE = '\033[1K'
BOLD='\033[1m'
RED = '\033[91m'
YELLOW = '\033[93m'
GREEN = '\033[92m'
BLUE = '\033[94m'
ENDC = '\033[0m'
SAVE_CURSOR='\033[s'		
UNSAVE_CURSOR='\033[u'		
CURSOR_HOME='\033[h'

def ok(text):
    return GREEN + text + ENDC

def warn(text):
    return YELLOW + text + ENDC

def fail(text):
    return RED + text + ENDC

def bold(text):
    return BOLD + text + ENDC

def cursor_position():
    sys.stdout.write('\033[6n')

def cursor_back(count):
    sys.stdout.write('\033[%sD'%count)

def printc(text):
    sys.stdout.write(text)

def print_progress(stats):
    sys.stdout.write(ERASE_START_OF_LINE)
    length = 0
    
    if stats.total:        
        processed = (stats.articles + 
                     stats.redirects +
                     stats.skipped +
                     stats.empty +
                     stats.timedout +
                     stats.failed
                     )
        progress = '%.2f' % (100*float(processed)/stats.total)
    else:
        progress = '?'
    text = '%s%% ' % progress
    length += len(text)
    printc(bold(text))

    text = 'articles: %d redirects: %d ' % (stats.articles, 
                                                      stats.redirects)
    length += len(text)
    printc(ok(text))

    text = 'skipped: %d ' % stats.skipped
    length += len(text)
    printc(warn(text))

    text = 'empty: %d ' % stats.empty
    length += len(text)
    printc(warn(text))

    text = 'timed out: %d ' % stats.timedout
    length += len(text)
    printc(warn(text))

    text = 'failed: %d ' % stats.failed
    length += len(text)
    printc(fail(text))
    cursor_back(length)
    sys.stdout.flush()

def erase_progress(progress):
    s = str(progress)
    sys.stdout.write('\b'*len(s))
    sys.stdout.flush()

def guess_version(input_file_name):
    """ Guess dictionary version from input file name.

    >>> guess_version('simplewiki-20090506-pages-articles.cdb')
    '20090506'

    >>> guess_version('~/wikidumps/simplewiki-20090506-pages-articles.cdb')
    '20090506'

    >>> guess_version('some-name')

    >>> guess_version('ruwiktionary-20090122-pages-articles.cdb')
    '20090122'

    """
    import re
    m = re.match(r'\w+-?(\d+)-?\w+', os.path.basename(input_file_name))
    return m.group(1) if m else None

def guess_wiki_lang(input_file_name):
    """ Guess wiki language from input file name.

    >>> guess_wiki_lang('simplewiki-20090506-pages-articles.cdb')
    'simple'
    >>> guess_wiki_lang('simplewiki-20090506-pages-articles.cdb/')
    'simple'
    >>> guess_wiki_lang('~/wikidumps/simplewiki-20090506-pages-articles.cdb')
    'simple'
    >>> guess_wiki_lang('elwiki-20090512-pages-articles')
    'el'
    >>> guess_wiki_lang('somename')

    >>> guess_wiki_lang('ruwiktionary-20090122-pages-articles')
    'ru'

    """
    import re
    m = re.match(r'([a-zA-Z]{2,})wik[i|t].*',
                 os.path.basename(input_file_name.rstrip(os.path.sep)))
    return m.group(1) if m else None

def msg(text):
    sys.stdout.write(text)
    sys.stdout.write('\n')
    sys.stdout.flush()

def main():

    opt_parser = make_opt_parser()
    options, args = opt_parser.parse_args()

    if not args:
        opt_parser.print_help()
        raise SystemExit(1)

    if len(args) < 2:
        sys.stderr.write('Not enough parameters\n')
        opt_parser.print_help()
        raise SystemExit(1)

    if args[0] not in known_types:
        sys.stderr.write('Unknown input type %s, expected one of %s\n' %
                         (args[0], ', '.join(known_types.keys())))
        opt_parser.print_help()
        raise SystemExit(1)

    input_type = args[0]
    input_files = args[1:]

    if not input_files:
        sys.stderr.write('No input files specified\n')
        raise SystemExit(1)

    if '-' in input_files and len(input_files) != 1:
        sys.stderr.write('stdin is specified as input file, but other files '
                         'are specified too (%s), can\'t proceed\n' % input_files)
        raise SystemExit(1)

    for input_file in input_files:
        if not input_file == '-' and not os.path.exists(input_file):
            sys.stderr.write('No such file: %s\n' % input_file)
            raise SystemExit(1)

    output_file_name = make_output_file_name(input_files[0], options)

    if options.quite:
        log_level = logging.ERROR
    elif options.debug:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO

    if options.log_file:
        log_file_name = options.log_file
    else:
        log_file_name = os.path.extsep.join((output_file_name, 'log'))

    print

    logging.getLogger().handlers[:] = []
    logging.basicConfig(format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
                        level=log_level,
                        filename=log_file_name,
                        datefmt="%X")
    logging.getLogger('multiprocessing').setLevel(logging.WARN)

    max_volume_size = max_file_size(options)
    log.info('Maximum file size is %d bytes', max_volume_size)
    if max_volume_size > MAX_FAT32_FILE_SIZE:
        global INDEX1_ITEM_FORMAT
        INDEX1_ITEM_FORMAT = '>LQ'
        log.info('Maximum file size is too big 32-bit offsets, '
                 'setting index item format to %s',
                 INDEX1_ITEM_FORMAT)

    if input_type=='wiki':
        if not options.wiki_lang:
            options.wiki_lang = guess_wiki_lang(input_files[0])
            if not options.wiki_lang:
                sys.stderr.write('Wiki language is neither specified with --wiki-lang '
                                 'not could be guessed from input file name\n')
                raise SystemExit(1)
        log.info('Wikipedia language: %s', options.wiki_lang)

    if not options.dict_ver:
        options.dict_ver = guess_version(input_files[0])
        if options.dict_ver:
            log.info('Using %s as dictionary version', options.dict_ver)
        else:
            options.dict_ver = time.strftime('%Y%m%d%H%M%S')
            log.warn('Dictionary version is not specified and couldn\'t '
                     'be guessed from input file name, using %s', options.dict_ver)

    metadata = {aardtools.__name__: aardtools.__version__}

    if options.license:
        with open(options.license) as f:
            metadata['license'] = f.read()

    if options.copyright:
        with open(options.copyright) as f:
            metadata['copyright'] = f.read()

    log.debug('Metadata: %s', metadata)

    session_dir = os.path.join(options.work_dir,
                               'aardc-'+('%.2f' % time.time()).replace('.','-'))

    if os.path.exists(session_dir):
        sys.stderr.write('Session directory %s already'
                         ' exists, can\'t proceed\n' % session_dir)
        raise SystemExit(1)
    else:
        log.info('Creating session dir %s', session_dir)
        os.mkdir(session_dir)

    compiler = Compiler(output_file_name, max_volume_size,
                        session_dir, metadata)
    make_input, collect_articles, total_func = known_types[input_type]

    t0 = time.time()
    msg('Converting %s' % ', '.join(input_files))

    if total_func:
        for input_file in input_files:
            compiler.stats.total += total_func(input_file, options)        
    msg('total: %d' % compiler.stats.total)

    for input_file in input_files:
        log.info('Collecting articles in %s', input_file)
        collect_articles(make_input(input_file), options, compiler)
        msg('')
    msg('Compiling .aar files')
    compiler.compile()
    shutil.rmtree(session_dir)
    log.info(compiler.stats)
    log.info('Compression: %s',
             ', '.join('%s - %d' % item
                      for item in compress_counts.iteritems()))
    dt = time.time() - t0
    log.info('Compilation took %.1f s', dt)
    msg('Compilation took %.1f s' % dt)

if __name__ == '__main__':
    main()
