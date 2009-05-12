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

from PyICU import Locale, Collator
import simplejson

from sortexternal import SortExternal
from aarddict.dictionary import HEADER_SPEC, spec_len, calcsha1

logging.basicConfig(format='%(levelname)s: %(message)s')
log = logging.getLogger()

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
        default=10.0,
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
        '--mem-check-freq',
        type='int',
        default=0,
        help=
        'Check memory usage every N articles. Set to 0 (zero) '
        'to disable. Default: %defaults'
        )
    parser.add_option(
        '--rss-threshold',
        type='float',
        default=0,
        help=
        'RSS (resident) memory threshold in megabytes for a single '
        'worker process. Worker process will be terminated if memory '
        'threshold is exceeded. Default: %defaults'
        )
    parser.add_option(
        '--rsz-threshold',
        type='float',
        default=0,
        help=
        'RSZ (resident + text) memory threshold in megabytes for a single '
        'worker process. Worker process will be terminated if memory '
        'threshold is exceeded. Default: %defaults'
        )

    parser.add_option(
        '--vsz-threshold',
        type='float',
        default=0,
        help=
        'VSZ (virtual) memory threshold in megabytes for a single '
        'worker process. Worker process will be terminated if memory '
        'threshold is exceeded. Default: %defaults'
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
        logging.info('Work dir %s', work_dir)
        self.header_meta_len = header_meta_len
        self.max_file_size = max_file_size
        self.index1 = tempfile.NamedTemporaryFile(prefix='aardc-index1-',
                                                  dir=work_dir)
        logging.info('Creating temporary index 1 file %s', self.index1.name)
        self.index2 = tempfile.NamedTemporaryFile(prefix='aardc-index2-',
                                                  dir=work_dir)
        logging.info('Creating temporary index 2 file %s', self.index2.name)
        self.articles =  tempfile.NamedTemporaryFile(prefix='aardc-articles-',
                                                     dir=work_dir)
        logging.info('Creating temporary articles file %s', self.articles.name)
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

class Compiler(object):

    def __init__(self, output_file_name, max_file_size, work_dir, metadata=None):
        self.uuid = uuid.uuid4()
        self.output_file_name = output_file_name
        self.max_file_size = max_file_size
        self.running_count = 0
        self.index_count = 0
        self.work_dir = work_dir
        self.sortex = SortExternal(work_dir=work_dir)
        self.tempDir = tempfile.mkdtemp(prefix='aardc-article-db-', dir=work_dir)
        logging.info('Creating temp dir %s', self.tempDir)
        self.indexDbFullname = os.path.join(self.tempDir, "index.db")
        self.indexDb = shelve.open(self.indexDbFullname, 'n')
        self.metadata = metadata if metadata is not None else {}
        self.file_names = []
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
    def add_article(self, title, serialized_article):
        with article_add_lock:
            if (not title) or (not serialized_article):
                log.debug('Skipped blank article: "%s" -> "%s"',
                          title, serialized_article)
                return

            if self.indexDb.has_key(title):
                articles = self.indexDb[title]
                log.debug('Adding article for "%s" (already have %d)',
                          title, len(articles))
            else:
                log.debug('Article for "%s"', title)
                collationKeyString4 = (collator4.
                                       getCollationKey(title).
                                       getByteArray())
                self.sortex.put(collationKeyString4 + "___" + title)
                articles = []
            articles.append(compress(serialized_article))
            self.indexDb[title] = articles
            print_progress(self.running_count)
            self.running_count += 1

    def compile(self):
        erase_progress(self.running_count)
        log.info('Sorting')
        self.sortex.sort()
        log.info('Compiling %s', self.output_file_name)
        metadata = compress(tojson(self.metadata))
        header_meta_len = spec_len(HEADER_SPEC) + len(metadata)
        create_volume_func = functools.partial(self.create_volume,
                                               header_meta_len)
        for volume in self.make_volumes(create_volume_func):
            log.info("Creating volume %d" % volume.number)
            self.make_aar(volume)
            log.info("Volume %d created" % volume.number)
        self.sortex.cleanup()
        self.indexDb.close()
        os.remove(self.indexDbFullname)
        os.rmdir(self.tempDir)
        self.write_volume_count()
        self.write_sha1sum()
        self.rename_files()

    def create_volume(self, header_meta_len):
        return Volume(header_meta_len, self.max_file_size, self.work_dir)

    def make_volumes(self, create_volume_func):

        volume = create_volume_func()

        for count, item in enumerate(self.sortex):
            print_progress(count)
            sortkey, title = item.split("___", 1)
            serialized_articles = self.indexDb[title]
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
                    erase_progress(count)
                    volume.flush()
                    yield volume
                    volume = create_volume_func()
                    index1Unit = struct.pack(INDEX1_ITEM_FORMAT,
                                             volume.index2Length,
                                             volume.articles_len)
                    volume.add(index1Unit, index2Unit, article_unit)

        erase_progress(count)
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
        index1.seek(0)
        writeCount = 0
        while True:
            print_progress(writeCount)
            unit = index1.read(struct.calcsize(INDEX1_ITEM_FORMAT))
            if len(unit) == 0:
                break
            index2ptr, offset = struct.unpack(INDEX1_ITEM_FORMAT, unit)
            unit = struct.pack(INDEX1_ITEM_FORMAT, index2ptr, offset)
            writeCount += 1
            output_file.write(unit)
        erase_progress(writeCount)
        log.debug('Wrote %d items to index 1', writeCount)
        index1.close()

    def write_index2(self, output_file, index2):
        log.debug('Writing index 2...')
        index2.seek(0)
        writeCount = 0
        while True:
            print_progress(writeCount)
            unitLengthString = index2.read(struct.calcsize(KEY_LENGTH_FORMAT))
            if len(unitLengthString) == 0:
                break
            writeCount += 1
            unitLength, = struct.unpack(KEY_LENGTH_FORMAT, unitLengthString)
            unit = index2.read(unitLength)
            output_file.write(unitLengthString + unit)
        erase_progress(writeCount)
        log.debug('Wrote %d items to index 2', writeCount)
        index2.close()

    def write_articles(self, output_file, articles):
        articles.seek(0)
        writeCount = 0
        while True:
            print_progress(writeCount)
            unitLengthString = articles.read(struct.
                                             calcsize(ARTICLE_LENGTH_FORMAT))
            if len(unitLengthString) == 0:
                break
            writeCount += 1
            unitLength, = struct.unpack(ARTICLE_LENGTH_FORMAT,
                                        unitLengthString)
            unit = articles.read(unitLength)
            output_file.write(unitLengthString + unit)
        erase_progress(writeCount)
        log.debug('Wrote %d items to articles', writeCount)
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
        self.file_names.append(file_name)
        log.info("Done with %s", file_name)

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
            os.rename(file_name, newname)
        else:
            for file_name in self.file_names:
                base, ext, vol = file_name.rsplit('.', 2)
                newname = "%s.%s_of_%s.%s" % (base,vol,Volume.number,ext)
                log.info('Renaming %s ==> %s', file_name, newname)
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
    if input_file_name == '-':
        return sys.stdin
    from bz2 import BZ2File
    try:
        bz2file = BZ2File(input_file_name)
        bz2file.readline()
    except:
        #probably this is not bz2, open regular file
        return open(input_file_name)
    else:
        bz2file.seek(0)
        return bz2file

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

known_types = {'wiki': (make_wiki_input, compile_wiki),
               'xdxf': (make_xdxf_input, compile_xdxf),
               'aard': (make_aard_input, compile_aard)}

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

def print_progress(progress):
    s = str(progress)
    sys.stdout.write('\b'*len(s) + s)
    sys.stdout.flush()

def erase_progress(progress):
    s = str(progress)
    sys.stdout.write('\b'*len(s))
    sys.stdout.flush()

def main():
    opt_parser = make_opt_parser()
    options, args = opt_parser.parse_args()

    if not args:
        opt_parser.print_help()
        raise SystemExit()

    if len(args) < 2:
        log.error('Not enough parameters')
        opt_parser.print_help()
        raise SystemExit()

    if args[0] not in known_types:
        log.error('Unknown input type %s, expected one of %s',
                  args[0], ', '.join(known_types.keys()))
        opt_parser.print_help()
        raise SystemExit()

    if options.quite:
        log.setLevel(logging.ERROR)
    elif options.debug:
        log.setLevel(logging.DEBUG)
    else:
        log.setLevel(logging.INFO)

    input_type = args[0]
    input_files = args[1:]

    if not input_files:
        log.error('No input files specified')
        raise SystemExit()

    if '-' in input_files and len(input_files) != 1:
        log.error('stdin is specified as input file, but other files '
                  'are specified too (%s), can''t proceed', input_files)
        raise SystemExit()

    for input_file in input_files:
        if not input_file == '-' and not os.path.isfile(input_file):
            log.error('No such file: %s', input_file)
            raise SystemExit()

    if input_type == 'wiki':
        if not options.templates:
            cdb_dir = os.path.extsep.join((strip_ext(input_files[0]),
                                           'cdb'))
            if os.path.isdir(cdb_dir):
                options.templates = cdb_dir
            else:
                cdb_dir = os.path.join(os.path.dirname(input_files[0]),
                                       cdb_dir)
                if os.path.isdir(cdb_dir):
                    options.templates = cdb_dir

        elif not os.path.isdir(options.templates):
            log.error("No such directory: %s", options.templates)
            raise SystemExit()
        if not options.templates:
            log.warn('\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n'
                     'Wikipedia templates database directory is not specified:\n'
                     'templates will not be processed.\n'
                     'Generate with mw-buildcdb, specify using -t option.\n'
                     '!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!'
                     )
        else:
            log.info('Using cdb in %s', options.templates)


    output_file_name = make_output_file_name(input_files[0], options)
    max_volume_size = max_file_size(options)
    log.info('Maximum file size is %d bytes', max_volume_size)
    if max_volume_size > MAX_FAT32_FILE_SIZE:
        global INDEX1_ITEM_FORMAT
        INDEX1_ITEM_FORMAT = '>LQ'
        log.info('Maximum file size is too big 32-bit offsets, '
                 'setting index item format to %s',
                 INDEX1_ITEM_FORMAT)

    metadata = {}
    if options.metadata:
        from ConfigParser import ConfigParser
        c = ConfigParser()
        c.read(options.metadata)
        for opt in c.options('metadata'):
            value = c.get('metadata', opt)
            metadata[opt] = value

    if options.license:
        with open(options.license) as f:
            metadata['license'] = f.read()

    if options.copyright:
        with open(options.copyright) as f:
            metadata['copyright'] = f.read()

    log.debug('Metadata: %s', metadata)

    compiler = Compiler(output_file_name, max_volume_size,
                        options.work_dir, metadata)
    make_input, collect_articles = known_types[input_type]
    import time
    t0 = time.time()
    for input_file in input_files:
        log.info('Collecting articles in %s', input_file)
        collect_articles(make_input(input_file), options, compiler)
    compiler.compile()
    log.info('Compression: %s',
             ', '.join('%s - %d' % item
                      for item in compress_counts.iteritems()))
    logging.info('Compilation took %.1f s', (time.time() - t0))


if __name__ == '__main__':
    main()
