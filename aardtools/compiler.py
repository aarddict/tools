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
import optparse
import functools
import time
import shutil
from datetime import timedelta

from PyICU import Locale, Collator
import simplejson

from aarddict.dictionary import (HEADER_SPEC, spec_len, calcsha1,
                                 collation_key, QUATERNARY)
import aardtools


log = logging.getLogger('compiler')

tojson = functools.partial(simplejson.dumps, ensure_ascii=False)

MAX_FAT32_FILE_SIZE = 2**32-1

KEY_LENGTH_FORMAT = '>H'
ARTICLE_LENGTH_FORMAT = '>L'
INDEX1_ITEM_FORMAT = '>LL'

def make_opt_parser():
    usage = "Usage: %prog [options] (wiki|xdxf|aard) FILE"
    parser = optparse.OptionParser(version="%prog "+aardtools.__version__, usage=usage)
    parser.add_option(
        '-o', '--output-file',
        default='',
        help=
        'Output file name. By default is the same as input '
        'file base name with .aar extension'
        )
    parser.add_option(
        '-s', '--max-file-size',
        default=str(2**31-1),
        help=
        'Maximum file size in bytes, kilobytes(K), megabytes(M) or gigabytes(G). '
        'Default: %default bytes'
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

    parser.add_option(
        '--show-legend',
        action='store_true',
        help='Show progress legend'
        )


    parser.add_option('--log-file',
                       help='Log file name. By default derived from output '
                       'file name by adding .log extension')

    parser.add_option('-r', '--remove-session-dir',
                      action='store_true',
                      help='Remove session directory after compilation.')

    parser.add_option(
        '--lang-links',
        help='Add Wikipedia language links to index for these languages '
        '(comma separated list of language codes)'
        )

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
        self.start_time = time.time()

    processed = property(lambda self: (self.articles +
                                       self.redirects +
                                       self.skipped +
                                       self.empty +
                                       self.timedout +
                                       self.failed))


    average = property(lambda self: (self.processed/(time.time() -
                                                     self.start_time)))

    elapsed = property(lambda self: timedelta(seconds=(int(time.time() -
                                                           self.start_time))))

    def __str__(self):
        return ('total: %d, skipped: %d, failed: %d, '
                'empty: %d, timed out: %d, articles: %d, '
                'redirects: %d, average: %.2f/s '
                'elapsed: %s' % (self.total,
                                 self.skipped,
                                 self.failed,
                                 self.empty,
                                 self.timedout,
                                 self.articles,
                                 self.redirects,
                                 self.average,
                                 self.elapsed))


import mmap

class TempArticleStore(object):

    def __init__(self, work_dir=None):
        fd, self.title_store_name = tempfile.mkstemp(prefix='aa-', suffix='.titles', dir=work_dir)
        self.title_store = os.fdopen(fd, 'w')
        fd, self.store_idx_name = tempfile.mkstemp(suffix='.index',
                                                   prefix='aa-', 
                                                   dir=work_dir)
        self.store_idx = os.fdopen(fd, 'wb')

        fd, self.article_store_name = tempfile.mkstemp(suffix='.articles',
                                                        prefix='aa-', 
                                                        dir=work_dir)
        self.article_store = os.fdopen(fd, 'wb')

        self.title_start = 0
        self.article_start = 0
        idx_format = '>IHQI'
        self.pack = functools.partial(struct.pack, idx_format)
        self.unpack = functools.partial(struct.unpack, idx_format)
        self.fmt_size = struct.calcsize(idx_format)

    def append(self, title, article):
        self.title_store.write(title)
        title_len = len(title)        
        
        self.article_store.write(article)
        article_len = len(article)        
        
        self.store_idx.write(self.pack(self.title_start, title_len, 
                                       self.article_start, article_len))

        self.title_start += title_len
        self.article_start += article_len
        

    def sorted(self, key=None):
        """ Return generator that produces ordered (title, article) 
        pairs sorted by title.

        :param key: function of one argument that takes article title 
                    and returns sort key for this title, title itself is used 
                    as key if key function is None        
        """

        self.title_store.flush()
        self.article_store.flush()
        self.store_idx.flush()

        if key is None:
            key = lambda x: x

        with open(self.title_store_name, 'r+') as title_store_f:
            with open(self.article_store_name, 'r+') as article_store_f:
                with open(self.store_idx_name, 'r+b') as store_idx_f:

                    title_store = mmap.mmap(title_store_f.fileno(), 0)
                    article_store = mmap.mmap(article_store_f.fileno(), 0)
                    store_idx = mmap.mmap(store_idx_f.fileno(), 0)

                    def index_item_at(pos):
                        pos_start = pos*self.fmt_size
                        pos_end = pos_start + self.fmt_size
                        return self.unpack(store_idx[pos_start:pos_end])


                    def realkey(x):
                        index_item = index_item_at(x)
                        title_start = index_item[0]
                        title_len = index_item[1]
                        title_end = title_start+title_len
                        title = title_store[title_start:title_end]
                        return key(title)

                    for i in sorted(xrange(len(store_idx)/self.fmt_size),
                                    key=realkey):
                        title_start, title_len, article_start, article_len = index_item_at(i)
                        yield (title_store[title_start:title_start+title_len], 
                               article_store[article_start:article_start+article_len])

    def close(self):
        self.title_store.close()
        self.article_store.close()
        self.store_idx.close()
        os.remove(self.title_store_name)
        os.remove(self.article_store_name)
        os.remove(self.store_idx_name)        

class Compiler(object):

    def __init__(self, output_file_name, max_file_size, session_dir, metadata=None):
        self.uuid = uuid.uuid4()
        self.output_file_name = output_file_name
        self.max_file_size = max_file_size
        self.index_count = 0
        self.session_dir = session_dir
        self.failed_articles = open(os.path.join(self.session_dir, "failed.txt"), 'w')
        self.empty_articles = open(os.path.join(self.session_dir, "empty.txt"), 'w')
        self.skipped_articles = open(os.path.join(self.session_dir, "skipped.txt"), 'w')
        self.metadata = metadata if metadata is not None else {}
        self.file_names = []
        self.stats = Stats()
        self.last_stat_update = 0
        self.article_store = TempArticleStore(self.session_dir)
        log.info('Collecting articles')

    def add_metadata(self, key, value):
        if key not in self.metadata:
            self.metadata[key] = value
        else:
            log.warn('Value for metadata key %s is already set, '
                     'new value %s will be ignored',
                     key, value)

    @utf8
    def add_article(self, title, serialized_article, redirect=False, count=True):
        with article_add_lock:
            if not title:
                log.warn('Blank title, ignoring article "%s"',
                         serialized_article)
                return
            if not serialized_article:
                self.empty_article(title)
                return
            log.debug('Adding article for "%s"', title)
            self.article_store.append(title, compress(serialized_article))
            if count:
                if not redirect:
                    self.stats.articles += 1
                else:
                    self.stats.redirects += 1
                self.print_stats()

    @utf8
    def fail_article(self, title):
        self.stats.failed += 1
        self.failed_articles.write(title+'\n')
        self.print_stats()

    @utf8
    def empty_article(self, title):
        self.stats.empty += 1
        self.empty_articles.write(title+'\n')
        self.print_stats()

    @utf8
    def skip_article(self, title):
        self.stats.skipped += 1
        self.skipped_articles.write(title+'\n')
        self.print_stats()

    def timedout(self, count=1):
        self.stats.timedout += count
        self.print_stats()

    def print_stats(self):
        t = time.time()
        if (t - self.last_stat_update) > 1.0:
            self.last_stat_update = t
            print_progress(self.stats)

    def compile(self):
        print_progress(self.stats)
        writeln()
        self.failed_articles.close()
        self.empty_articles.close()
        self.skipped_articles.close()
        writeln('Compiling .aar files')
        self.add_metadata("article_count", self.stats.articles)
        articles = self.article_store.sorted(key=lambda x:
                                                 collation_key(x).getByteArray())
        log.info('Compiling %s', self.output_file_name)
        metadata = compress(tojson(self.metadata).encode('utf8'))
        header_meta_len = spec_len(HEADER_SPEC) + len(metadata)
        create_volume_func = functools.partial(self.create_volume,
                                               header_meta_len)
        for volume in self.make_volumes(create_volume_func, articles):
            m = "Creating volume %d" % volume.number
            log.info(m)
            writeln(m).flush()
            file_name = self.make_aar(volume)
            self.file_names.append(file_name)
            m = "Wrote volume %d" % volume.number
            log.info(m)
            writeln(m).flush()
        self.article_store.close()
        self.write_volume_count()
        self.write_sha1sum()
        rename_files(self.file_names)

    def create_volume(self, header_meta_len):
        return Volume(header_meta_len, self.max_file_size, self.session_dir)

    def make_volumes(self, create_volume_func, articles):
        volume = create_volume_func()
        for title, serialized_article in articles:
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
            msg = "Calculating checksum for %s" % file_name
            log.info(msg)
            offset = spec_len(HEADER_SPEC[:2])
            st_size = os.stat(file_name).st_size
            size = float(st_size - offset)
            for pos, sha1sum in calcsha1(file_name, offset):
                (display.erase_line().cr()
                .write(msg).write(': ').write('%.1f%%' % (100*pos/size)))
            sha1sum = sha1sum.hexdigest()
            msg = "%s sha1: %s" % (file_name, sha1sum)
            log.info(msg)
            display.erase_line().cr().writeln(msg)
            output_file = open(file_name, "r+b")
            output_file.seek(spec_len(HEADER_SPEC[:1]))
            output_file.write(sha1sum)
            output_file.close()

    def make_aar(self, volume):
        (index1, index1Length, index2, index2Length, articles,
         articles_len, index_count) = volume.totuple()
        file_name = '%s.%d' % (self.output_file_name, Volume.number)
        output_file = open(file_name, "wb", 8192)
        metadata = compress(tojson(self.metadata).encode('utf8'))
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

def rename_files(file_names):
    """
    >>> from minimock import mock
    >>> import compiler
    >>> mock('compiler.rename_file', returns_func=lambda f, p, args: None)
    >>> Volume.number = 2
    >>> rename_files(['enwiki-20090530-2.aar.1'])
    Called compiler.rename_file(
        'enwiki-20090530-2.aar.1',
        '%s.%s',
        ('enwiki-20090530-2', 'aar'))

    >>> rename_files(['enwiki-20090530-2.aar.1', 'enwiki-20090530-2.aar.2'])
    Called compiler.rename_file(
        'enwiki-20090530-2.aar.1',
        '%s.%s_of_%s.%s',
        ('enwiki-20090530-2', '1', 2, 'aar'))
    Called compiler.rename_file(
        'enwiki-20090530-2.aar.2',
        '%s.%s_of_%s.%s',
        ('enwiki-20090530-2', '2', 2, 'aar'))

    >>> rename_files(['enwiki-20090530-2.1', 'enwiki-20090530-2.2'])
    Called compiler.rename_file(
        'enwiki-20090530-2.1',
        '%s.%s_of_%s.%s',
        ('enwiki-20090530-2', '1', 2, 'aar'))
    Called compiler.rename_file(
        'enwiki-20090530-2.2',
        '%s.%s_of_%s.%s',
        ('enwiki-20090530-2', '2', 2, 'aar'))

    """
    one = len(file_names) == 1
    pattern = '%s.%s' if one else '%s.%s_of_%s.%s'
    for file_name in file_names:
        if file_name.count('.') == 1:
            base, vol = file_name.split('.')
            ext = 'aar'
        else:
            base, ext, vol = file_name.rsplit('.', 2)
        args = (base, ext) if one else (base, vol, Volume.number, ext)
        rename_file(file_name, pattern, args)

def rename_file(file_name, newname_pattern, args):
    newname = newname_pattern % args
    log.info('Renaming %s ==> %s', file_name, newname)
    display.write('Created ').bold(newname).writeln()
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


collation_key = functools.partial(collation_key, strength=QUATERNARY)

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
        output_file = strip_ext(input_file.rstrip(os.path.sep))
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
    >>> strip_ext('/a/b/c/a.cdb/')
    'a'

    """
    output_file = os.path.basename(fname.rstrip(os.path.sep))
    output_file = output_file[:output_file.rfind('.')]
    if (output_file.endswith('.tar') or
        output_file.endswith('.xml') or
        output_file.endswith('.xdxf')):
        output_file = output_file[:output_file.rfind('.')]
    return output_file


def max_file_size(options):
    s = options.max_file_size
    return parse_size(s)

def parse_size(s):
    if s.endswith('M'):
        return int(s.strip('M'))*1024*1024
    elif s.endswith('G'):
        return int(s.strip('G'))**1024*1024*1024
    elif s.endswith('K'):
        return int(s.strip('K'))*1024
    elif s.endswith('m'):
        return int(s.strip('m'))*1000*1000
    elif s.endswith('g'):
        return int(s.strip('g'))*1000*1000*1000
    elif s.endswith('k'):
        return int(s.strip('k'))*1000
    elif s.endswith('b'):
        return int(s.strip('b'))
    else:
        return int(s)

class Display:

    ERASE_LINE = '\033[2K'
    BOLD='\033[1m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    GREEN = '\033[92m'
    ENDC = '\033[0m'

    def reset_att(self):
        sys.stdout.write(self.ENDC)
        return self

    def ok(self, text):
        sys.stdout.write(self.GREEN + text + self.ENDC)
        return self

    def warn(self, text):
        sys.stdout.write(self.YELLOW + text + self.ENDC)
        return self

    def fail(self, text):
        sys.stdout.write(self.RED + text + self.ENDC)
        return self

    def bold(self, text):
        sys.stdout.write(self.BOLD + text + self.ENDC)
        return self

    def erase_line(self):
        sys.stdout.write(self.ERASE_LINE)
        return self

    def write(self, text):
        sys.stdout.write(text)
        return self

    def writeln(self, text=''):
        self.write(text)
        sys.stdout.write('\n')
        return self

    def cr(self):
        sys.stdout.write('\r')
        return self

    def flush(self):
        sys.stdout.flush()
        return self

display = Display()
writeln = display.writeln

def print_legend():
    (display
    .bold('t').writeln(' - time elapsed')
    .bold('avg').writeln(' - average number of articles processed per second')
    .ok('a').writeln(' - number of processed articles')
    .ok('r').writeln(' - number of processed redirects')
    .warn('s').writeln(' - number of skipped articles')
    .warn('e').writeln(' - number of articles with no text (empty)')
    .fail('to').writeln(' - approximate number of articles that couldn\'t be converted fast enough (timed out)')
    .fail('f').writeln(' - number of articles that couldn\'t be converted (failed)'))


def print_progress(stats):
    try:
        progress = '%.2f' % (100*float(stats.processed)/stats.total) if stats.total else '?'
        (display
         .erase_line()
         .bold('%s%% ' % progress)
         .bold('t: %s ' % stats.elapsed)
         .bold('avg: %.1f/s ' % stats.average)
         .ok('a: %d r: %d ' % (stats.articles, stats.redirects))
         .warn('s: %d ' % stats.skipped)
         .warn('e: %d ' % stats.empty)
         .fail('to: %d ' % stats.timedout)
         .fail('f: %d ' % stats.failed)
         .cr().flush())
    except KeyboardInterrupt:
        display.reset_att()


def guess_version(input_file_name):
    """ Guess dictionary version from input file name.

    >>> guess_version('simplewiki-20090506-pages-articles.cdb')
    '20090506'

    >>> guess_version('~/wikidumps/simplewiki-20090506-pages-articles.cdb/')
    '20090506'

    >>> guess_version('~/wikidumps/simplewiki-20090506-pages-articles.cdb')
    '20090506'

    >>> guess_version('some-name')

    >>> guess_version('ruwiktionary-20090122-pages-articles.cdb')
    '20090122'

    """
    import re
    m = re.match(r'\w+-?(\d+)-?\w+',
                 os.path.basename(input_file_name.rstrip(os.path.sep)))
    return m.group(1) if m else None

def guess_wiki_lang(input_file_name):
    """ Guess wiki language from input file name.

    >>> guess_wiki_lang('simplewiki-20090506-pages-articles.cdb')
    'simple'
    >>> guess_wiki_lang('simplewiki-20090506-pages-articles.cdb/')
    'simple'
    >>> guess_wiki_lang('~/wikidumps/simplewiki-20090506-pages-articles.cdb/')
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

    session_dir = os.path.join(options.work_dir,
                               'aardc-'+('%.2f' % time.time()).replace('.','-'))

    if os.path.exists(session_dir):
        sys.stderr.write('Session directory %s already'
                         ' exists, can\'t proceed\n' % session_dir)
        raise SystemExit(1)
    else:
        os.mkdir(session_dir)
        display.write('Session dir ').bold(session_dir).writeln()


    try:
        converter = __import__(input_type, globals=globals())
    except ImportError:
        sys.stderr.write('Unknown input type %s\n' % args[0])
        opt_parser.print_help()
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
        log_file_name = os.path.join(session_dir, 'log')

    display.write('Writing log to ').bold(log_file_name).writeln()
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


    compiler = Compiler(output_file_name, max_volume_size,
                        session_dir, metadata)


    t0 = time.time()
    display.write('Converting ').bold(', '.join(input_files)).writeln()

    if hasattr(converter, 'total'):
        display.write('Calculating total number of articles...').cr().flush()
        for input_file in input_files:
            compiler.stats.total += converter.total(converter.make_input(input_file), options)
    display.erase_line().writeln('total: %d' % compiler.stats.total)

    if options.show_legend:
        print_legend()

    for input_file in input_files:
        log.info('Collecting articles in %s', input_file)
        converter.collect_articles(converter.make_input(input_file), options, compiler)
    compiler.compile()
    if options.remove_session_dir:
        writeln('Removing session dir')
        shutil.rmtree(session_dir)
    log.info(compiler.stats)
    log.info('Compression: %s',
             ', '.join('%s - %d' % item
                      for item in compress_counts.iteritems()))
    log.info('Compilation took %s', timedelta(seconds=time.time() - t0))
    writeln('Compilation took %s' % timedelta(seconds=int(time.time() - t0)))


if __name__ == '__main__':
    main()
