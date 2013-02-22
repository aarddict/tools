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
# Copyright (C) 2008-2009  Jeremy Mortis
# Copyright (C) 2008-2013  Igor Tkach


import argparse
import functools
import json
import logging
import mmap
import os
import shutil
import struct
import sys
import tempfile
import time
import uuid

from datetime import timedelta

from icu import Locale, Collator


from aarddict.dictionary import HEADER_SPEC, spec_len, calcsha1, collation_key
import aardtools


log = logging.getLogger('compiler')

tojson = functools.partial(json.dumps, ensure_ascii=False)

MAX_FAT32_FILE_SIZE = 2**32-1

KEY_LENGTH_FORMAT = '>H'
ARTICLE_LENGTH_FORMAT = '>L'
INDEX1_ITEM_FORMAT = '>LL'

from abc import ABCMeta, abstractmethod, abstractproperty
import collections


class Article(object):

    def __init__(self, title, text,
                 isredirect=False, counted=True,
                 failed=False, skipped=False):
        """
        Parameters:

        title
          Article title, unicode or utf8-encoded string

        text
          Article text, unicode or utf8-encoded string

        redirect
          Whether this entry is a redirect. Compiler is only interested in this
          for statistical purposes.

        counted
          Whether this entry is included in total article count

          Some redirects may be generated based on parsed article text
          to provide additional keywords to look up an article (such as
          titles in other languages derived from language links in
          wikipedia articles) and where not included in total article
          count reported by article source.

        failed
          True if article conversion failed with an error

        skipped
          True if article source skipped the article

        """
        self.title = title
        self.text = text
        self.isredirect = isredirect
        self.counted = counted
        self.failed = failed
        self.skipped = skipped

    @property
    def empty(self):
        return not self.text or not self.title


class ArticleSource(collections.Iterable):

    """
    Base class for article sources. Optionally
    article source class may extend collections.Sized
    to allow queirying for total number of articles
    """
    __metaclass__ = ABCMeta

    @classmethod
    @abstractmethod
    def name(cls):
        """
        Return name of this article source
        """
        return "XYZZ"

    @classmethod
    @abstractmethod
    def register_args(cls, parser):
        """
        Adds command line argument definitions to
        provided instance of argparse subparser, to be used
        for parsing this article source's command line args.

        """

    @abstractmethod
    def __init__(self, args):
        """
        Constructor to initialize this article source
        with command line args parsed with provided arg parser

        """

    @abstractproperty
    def metadata(self):
        """
        Metadata to be added to resulting dictionary,
        simple dictionary.

        """
        return {}


class DummyArticleSource(ArticleSource, collections.Sized):

    @classmethod
    def name(cls):
        return 'dummy'

    @classmethod
    def register_args(cls, parser):
        parser.add_argument(
            '--len',
            type=int,
            default=100,
            help= 'Number of "articles" in dummy source')

    def __init__(self, args):
        super(DummyArticleSource, self).__init__(self)
        self.len = args.len

    def __len__(self):
        return self.len

    @property
    def metadata(self):
        return {}

    def __iter__(self):
        for i in range(len(self)):
            title = 'title %s' % i
            text = 'article %s' %i
            if i % 4 == 0:
                yield Article(title, None, failed=True)
            elif i % 4 == 1:
                yield Article(title, None)
            elif i % 4 == 2:
                yield Article(title, None, skipped=True)
            else:
                yield Article(title, json.dumps((text, [])))


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


    def __init__(self, dictionary_uuid, header_meta_len, max_file_size_, work_dir):
        self.dictionary_uuid = dictionary_uuid
        self.header_meta_len = header_meta_len
        self.max_file_size = max_file_size_
        self.work_dir = work_dir
        self.index1 = tempfile.NamedTemporaryFile(prefix='index1',
                                                  dir=work_dir,
                                                  delete=False)
        log.info('Creating temporary index 1 file %s', self.index1.name)
        self.index2 = tempfile.NamedTemporaryFile(prefix='index2',
                                                  dir=work_dir,
                                                  delete=False)
        log.info('Creating temporary index 2 file %s', self.index2.name)
        self.articles =  tempfile.NamedTemporaryFile(prefix='articles',
                                                     dir=work_dir,
                                                     delete=False)
        log.info('Creating temporary articles file %s', self.articles.name)

        self.index1_sorted = None

        self.index1Length = 0
        self.index2Length = 0
        self.articles_len = 0
        self.index_count = 0
        Volume.number += 1


    def add(self, title, serialized_article):
        index1Unit = struct.pack(INDEX1_ITEM_FORMAT,
                                 self.index2Length,
                                 self.articles_len)
        index2Unit = struct.pack(KEY_LENGTH_FORMAT, len(title)) + title
        article_unit = (struct.pack(ARTICLE_LENGTH_FORMAT,
                                   len(serialized_article)) +
                        serialized_article)
        self._add(index1Unit, index2Unit, article_unit)


    def _add(self, index1_unit, index2_unit, article_unit):
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


    def _sort(self):
        index1_sorted = tempfile.NamedTemporaryFile(prefix='index1_sorted',
                                                    dir=self.work_dir,
                                                    delete=False)
        self.index1_sorted = index1_sorted
        index1_unit_len = struct.calcsize(INDEX1_ITEM_FORMAT)
        klen_structsize = struct.calcsize(KEY_LENGTH_FORMAT)

        key = lambda x: collation_key(x).getByteArray()

        with open(self.index1.name) as fi1, open(self.index2.name) as fi2:

            index1 = mmap.mmap(fi1.fileno(), 0, prot=mmap.PROT_READ)
            index2 = mmap.mmap(fi2.fileno(), 0, prot=mmap.PROT_READ)

            index_item_count = len(index1)/index1_unit_len

            def read_packed_index1_item(i):
                pos_start = i*index1_unit_len
                pos_end = pos_start + index1_unit_len
                return index1[pos_start:pos_end]

            def index1_item_at(i):
                return struct.unpack(INDEX1_ITEM_FORMAT,
                                     read_packed_index1_item(i))

            def read_key(pos):
                start = pos+klen_structsize
                s = index2[pos:start]
                strlen = struct.unpack(KEY_LENGTH_FORMAT, s)[0]
                return index2[start:start+strlen]

            def realkey(x):
                index_item = index1_item_at(x)
                index2_ptr = index_item[0]
                title = read_key(index2_ptr)
                return key(title)

            def sorted_index1_items():
                for i in sorted(xrange(index_item_count), key=realkey):
                    yield read_packed_index1_item(i)

            for index1_item in sorted_index1_items():
                index1_sorted.write(index1_item)

            index1_sorted.close()
        log.info("Index sorted, removing temp file %s", self.index1.name)
        os.remove(self.index1.name)

    #FIXME currently metadata is processed after all articles collected
    #but now we want to create Volume right away, so we need to know
    #metadata length before we start with articles... sort of - that's only
    #to detect when we exceed desired volume size
    def finalize(self, output_file_name, serialized_metadata):
        self.index1.close()
        self.index2.close()
        self.articles.close()
        self._sort()
        file_name = '%s.%d' % (output_file_name, Volume.number)
        buf_size = 1024*1024
        with open(file_name, "wb", buf_size) as output_file:
            self.write_header_and_meta(output_file, serialized_metadata)
            for fname in (self.index1_sorted.name, self.index2.name, self.articles.name):
                with open(fname) as f:
                    while True:
                        data = f.read(buf_size)
                        if len(data) == 0:
                            break
                        output_file.write(data)
        log.info("Done with %s", file_name)
        log.info("Removing temp file %s", self.index1_sorted.name)
        os.remove(self.index1_sorted.name)
        log.info("Removing temp file %s", self.index2.name)
        os.remove(self.index2.name)
        log.info("Removing temp file %s", self.articles.name)
        os.remove(self.articles.name)
        return file_name

    def write_header_and_meta(self, output_file, serialized_metadata):
        meta_length = len(serialized_metadata)
        article_offset = (spec_len(HEADER_SPEC) + meta_length +
                          self.index1Length + self.index2Length)
        values = dict(signature='aard',
                      sha1sum='0'*40,
                      version=1,
                      uuid=self.dictionary_uuid.bytes,
                      volume=self.number,
                      of=0,
                      total_volumes=0,
                      meta_length=meta_length,
                      index_count=self.index_count,
                      article_offset=article_offset,
                      index1_item_format=INDEX1_ITEM_FORMAT,
                      key_length_format=KEY_LENGTH_FORMAT,
                      article_length_format=ARTICLE_LENGTH_FORMAT)
        for name, fmt in HEADER_SPEC:
            output_file.write(struct.pack(fmt, values[name]))
        output_file.write(serialized_metadata)


import threading
article_add_lock = threading.RLock()

class Stats(object):

    def __init__(self):
        self.total = 0
        self.skipped = 0
        self.failed = 0
        self.empty = 0
        self.articles = 0
        self.redirects = 0
        self.start_time = time.time()
        self.article_start_time = 0

    processed = property(lambda self: (self.articles +
                                       self.redirects +
                                       self.skipped +
                                       self.empty +
                                       self.failed))


    average = property(lambda self: (self.processed/(time.time() -
                                                     self.article_start_time)))

    elapsed = property(lambda self: timedelta(seconds=(int(time.time() -
                                                           self.start_time))))

    def __str__(self):
        return ('total: %d, skipped: %d, failed: %d, '
                'empty: %d, articles: %d, '
                'redirects: %d, average: %.2f/s '
                'elapsed: %s' % (self.total,
                                 self.skipped,
                                 self.failed,
                                 self.empty,
                                 self.articles,
                                 self.redirects,
                                 self.average,
                                 self.elapsed))


class Compiler(object):

    def __init__(self, article_source, output_file_name,
                 max_file_size_, session_dir, metadata=None):
        self.uuid = uuid.uuid4()
        self.output_file_name = output_file_name
        self.max_file_size = max_file_size_
        self.index_count = 0
        self.session_dir = session_dir
        self.failed_articles = open(os.path.join(self.session_dir, "failed.txt"), 'w')
        self.empty_articles = open(os.path.join(self.session_dir, "empty.txt"), 'w')
        self.skipped_articles = open(os.path.join(self.session_dir, "skipped.txt"), 'w')
        self.metadata = metadata if metadata is not None else {}
        self.file_names = []
        self.stats = Stats()
        if isinstance(article_source, collections.Sized):
            writeln('Calculating total number of items...')
            self.stats.total = len(article_source)
        #this is just placeholder value to we pad metadata size enough
        #so that final volume file size does not exceed specified limit
        self.metadata["article_count"] = int(1e+16)
        #article_count used to mean dictionary total
        #allow readers distinguish between the two
        self.metadata["article_count_is_volume_total"] = True
        self.last_stat_update = 0
        self.article_source = article_source
        log.info('Collecting metadata...')
        if self.article_source.metadata:
            for k, v in self.article_source.metadata.iteritems():
                self.add_metadata(k, v)
        log.info('Metadata collected')
        self.current_volume = None
        self.current_volume_article_count = 0

    def run(self):
        for article in self.article_source:
            title = article.title
            if article.failed:
                self.fail_article(title)
            elif article.skipped:
                self.skip_article(title)
            elif article.empty:
                self.empty_article(title)
            else:
                self.add_article(title, article.text,
                                 redirect=article.isredirect, count=article.counted)
        self.finalize_current_volume()
        self.write_volume_count()
        self.write_sha1sum()
        rename_files(self.file_names)

    def finalize_current_volume(self):
        if self.current_volume:
            self.print_stats(force=True)
            writeln()
            m = "Finalizing volume %d" % self.current_volume.number
            log.info(m)
            writeln(m).flush()
            self.metadata['article_count'] = self.current_volume_article_count
            file_name = self.current_volume.finalize(self.output_file_name,
                                                     self.serialized_metadata)
            self.file_names.append(file_name)
            m = "Wrote volume %d" % self.current_volume.number
            log.info(m)
            writeln(m).flush()
            self.current_volume = None
            self.current_volume_article_count = 0

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

            if self.current_volume is None:
                self.current_volume = self.create_volume()

            if not title:
                log.warn('Blank title, ignoring article "%s"',
                         serialized_article)
                return
            if not serialized_article:
                self.empty_article(title)
                return
            log.debug('Adding article for "%s"', title)
            try:
                self.current_volume.add(title, compress(serialized_article))
            except Volume.ExceedsMaxSize:
                self.finalize_current_volume()
                self.add_article(title, serialized_article, redirect=redirect, count=count)
                return
            if count:
                if not redirect:
                    self.stats.articles += 1
                    self.current_volume_article_count += 1
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

    def print_stats(self, force=False):
        t = time.time()
        if force or (t - self.last_stat_update) > 1.0:
            self.last_stat_update = t
            print_progress(self.stats)

    def create_volume(self):
        header_meta_len = spec_len(HEADER_SPEC) + len(self.serialized_metadata)
        return Volume(self.uuid,
                      header_meta_len,
                      self.max_file_size,
                      self.session_dir)

    @property
    def serialized_metadata(self):
        return compress(tojson(self.metadata).encode('utf8'))

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

    def write_volume_count(self):
        _name, fmt = HEADER_SPEC[5]
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


collator = Collator.createInstance(Locale(''))
collator.setStrength(Collator.QUATERNARY)
collation_key = collator.getCollationKey


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

    >>> guess_version('ruwiktionary-20090122-1.cdb')
    '20090122'

    >>> guess_version('ruwiktionary-20090122.cdb')
    '20090122'

    """
    import re
    m = re.match(r'\w+-?(\d+)[^\d]*',
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


def make_argparser():

    parser = argparse.ArgumentParser()

    parser.add_argument('--version', action='version', version=aardtools.__version__)

    parser.add_argument(
        '-o', '--output-file',
        default='',
        help=
        'Output file name. By default is the same as input '
        'file base name with .aar extension'
        )

    parser.add_argument(
        '-s', '--max-file-size',
        default=str(2**31-1),
        help=
        'Maximum file size in bytes, kilobytes(K), megabytes(M) or gigabytes(G). '
        'Default: %(default)s bytes'
        )

    parser.add_argument(
        '-d', '--debug',
        action='store_true',
        default=False,
        help='Turn on debugging messages'
        )

    parser.add_argument(
        '-q', '--quite',
        action='store_true',
        default=False,
        help='Print minimal information about compilation progress'
        )

    parser.add_argument(
        '--work-dir',
        default='.',
        help=
        'Directory for temporary file created during compilatiod. '
        'Default: %(default)s'
        )

    parser.add_argument(
        '--show-legend',
        action='store_true',
        help='Show progress legend'
        )

    parser.add_argument('--log-file',
                       help='Log file name. By default derived from output '
                       'file name by adding .log extension')

    parser.add_argument('-r', '--remove-session-dir',
                      action='store_true',
                      help='Remove session directory after compilation.')

    parser.add_argument(
        '--metadata',
        default=None,
        help='INI containing dictionary metadata in [metadata] section'
        )
    parser.add_argument(
        '--license',
        default=None,
        help='Name of a UTF-8 encoded text file containing license text'
        )
    parser.add_argument(
        '--copyright',
        default=None,
        help='Name of a UTF-8 encoded text file containing copyright notice'
        )

    parser.add_argument(
        '--dict-ver',
        help='Version of the compiled dictionary'
        )

    parser.add_argument(
        '--dict-update',
        default='1',
        help='Update number for the compiled dictionary. Default: %(default)s'
        )


    return parser

def main():

    argparser = make_argparser()

    parent_parser = argparse.ArgumentParser(add_help=False)

    parent_parser.add_argument(
            'input_files',
            nargs='+',
            help='Path(s) to input file')

    subparsers = argparser.add_subparsers(title='converters',
                                          description='Available article source types')

    parser_parents = [parent_parser]

    from aardtools.wiki.wiki import MediawikiArticleSource
    from aardtools.xdxf import XdxfArticleSource
    from aardtools.wordnet import WordNetArticleSource
    from aardtools.aard import AardArticleSource

    for cls in (MediawikiArticleSource,
                XdxfArticleSource,
                WordNetArticleSource,
                AardArticleSource,
                DummyArticleSource):
        parser = subparsers.add_parser(cls.name(), parents=parser_parents)
        cls.register_args(parser)
        parser.set_defaults(article_source_class=cls)

    args = argparser.parse_args()

    input_files = args.input_files

    #TODO replace all regs to "options" with args
    options = args

    session_dir = os.path.join(options.work_dir,
                               'aardc-'+('%.2f' % time.time()).replace('.','-'))

    if os.path.exists(session_dir):
        sys.stderr.write('Session directory %s already'
                         ' exists, can\'t proceed\n' % session_dir)
        raise SystemExit(1)
    else:
        os.mkdir(session_dir)
        display.write('Session dir ').bold(session_dir).writeln()


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
    root_logger = logging.getLogger()
    root_logger.handlers[:] = []
    logging.basicConfig(format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
                        level=log_level,
                        filename=log_file_name,
                        datefmt="%X")
    multiprocessing_logger = logging.getLogger('multiprocessing')
    #multiprocessing is noisy at info level
    multiprocessing_logger.setLevel(logging.WARNING)
    multiprocessing_logger.handlers = root_logger.handlers

    max_volume_size = max_file_size(options)
    log.info('Maximum file size is %d bytes', max_volume_size)
    if max_volume_size > MAX_FAT32_FILE_SIZE:
        global INDEX1_ITEM_FORMAT
        INDEX1_ITEM_FORMAT = '>LQ'
        log.info('Maximum file size is too big 32-bit offsets, '
                 'setting index item format to %s',
                 INDEX1_ITEM_FORMAT)

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


    article_source = args.article_source_class(args)

    display.write('Converting ').bold(', '.join(input_files)).writeln()

    compiler = Compiler(article_source, output_file_name, max_volume_size,
                        session_dir, metadata)

    display.erase_line().writeln('total: %d' % compiler.stats.total)

    if options.show_legend:
        print_legend()

    t0 = time.time()
    compiler.stats.article_start_time = t0
    compiler.run()

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
