#!/usr/bin/python

"""
This file is part of Aarddict Dictionary Viewer
(http://code.google.com/p/aarddict)

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation version 3 of the License.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.

Copyright (C) 2008  Jeremy Mortis and Igor Tkach
"""
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
import aarddict
from aarddict.dictionary import HEADER_SPEC, spec_len

logging.basicConfig(format='%(levelname)s: %(message)s')
log = logging.getLogger()

tojson = functools.partial(simplejson.dumps, ensure_ascii=False) 

KEY_LENGTH_FORMAT = '>H'
ARTICLE_LENGTH_FORMAT = '>L'
INDEX1_ITEM_FORMAT = '>LL'

def make_opt_parser():
    usage = "usage: %prog [options] (wiki|xdxf) FILE"
    parser = optparse.OptionParser(version="%prog 1.0", usage=usage)
    parser.add_option(
        '-o', '--output-file',
        default='',
        help='Output file name. By default is the same as input file base name with .aar extension'
        )
    parser.add_option(
        '-s', '--max-file-size',
        default='2000M',
        help='Maximum file size in megabytes(M) or gigabytes(G). Default: %default'
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
        help='Skip article if it was not process in the amount of time specified.'
        )
    parser.add_option(
        '--processes',
        type='int',
        default=None,
        help='Size of the worker pool (by default equals to the number of detected CPUs). '
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
    
    def __init__(self, header_meta_len, max_file_size):
        self.header_meta_len = header_meta_len
        self.max_file_size = max_file_size
        self.index1 = tempfile.NamedTemporaryFile()
        self.index2 = tempfile.NamedTemporaryFile()
        self.articles =  tempfile.NamedTemporaryFile()
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
    
    def __init__(self, output_file_name, max_file_size):
        self.uuid = uuid.uuid4()
        self.output_file_name = output_file_name
        self.max_file_size = max_file_size        
        self.running_count = 0
        self.index_count = 0
        self.sortex = SortExternal()
        self.tempDir = tempfile.mkdtemp()
        self.indexDbFullname = os.path.join(self.tempDir, "index.db")
        self.indexDb = shelve.open(self.indexDbFullname, 'n')
        self.metadata = {}
        self.file_names = []        
        log.info('Collecting articles')
    
    @utf8
    def add_metadata(self, key, value):
        self.metadata[key] = value

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
                collationKeyString4 = collator4.getCollationKey(title).getByteArray()        
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
        create_volume_func = functools.partial(self.create_volume, header_meta_len)     
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
        return Volume(header_meta_len, self.max_file_size)
    
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
                article_unit = struct.pack(ARTICLE_LENGTH_FORMAT, 
                                           len(serialized_article)) + serialized_article
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
            unitLengthString = articles.read(struct.calcsize(ARTICLE_LENGTH_FORMAT))
            if len(unitLengthString) == 0:
                break
            writeCount += 1
            unitLength, = struct.unpack(ARTICLE_LENGTH_FORMAT, unitLengthString)
            unit = articles.read(unitLength)
            output_file.write(unitLengthString + unit)
        erase_progress(writeCount)
        log.debug('Wrote %d items to articles', writeCount)
        articles.close()

    def write_sha1sum(self):
        for file_name in self.file_names:
            log.info("Calculating checksum for %s", file_name)
            offset = spec_len(HEADER_SPEC[:2])                
            sha1sum = aarddict.dictionary.calcsha1(file_name, offset)
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
                                    
        
def compress(text):
    compressed = text
    for compress in aarddict.compression:
        c = compress(text)
        if len(c) < len(compressed):
            compressed = c
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

known_types = {'wiki': (make_wiki_input, compile_wiki), 
               'xdxf': (make_xdxf_input, compile_xdxf)}

def make_output_file_name(input_file, options):    
    if options.output_file:
        output_file = options.output_file
    elif input_file == '-':
        output_file = 'dictionary.aar'
    else:
        output_file = os.path.basename(input_file)
        output_file = output_file[:output_file.rfind('.')]
        if (output_file.endswith('.tar') or 
            output_file.endswith('.xml') or
            output_file.endswith('.xdxf')):
            output_file = output_file[:output_file.rfind('.')]
        output_file += '.aar'
    return output_file 

def max_file_size(options):
    s = options.max_file_size
    s = s.lower()
    if s.endswith('m'):        
        return int(s.strip('mM'))*1000000
    elif s.endswith('g'):
        return int(s.strip('gG'))*1000000000
    else:
        raise Exception('Can\'t understand maximum file size specification "%s"' % options.max_file_size)
        
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
    
    if len(args) != 2:
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
    input_file = args[1]    
    output_file_name = make_output_file_name(input_file, options)    
    max_volume_size = max_file_size(options)    
    log.info('Maximum file size is %d bytes', max_volume_size)    
    compiler = Compiler(output_file_name, max_volume_size)
    make_input, collect_articles = known_types[input_type]
    import time    
    t0 = time.time()
    collect_articles(make_input(input_file), options, compiler)
    compiler.compile()
    logging.info('Compilation took %.1f s', (time.time() - t0))    
    

if __name__ == '__main__':
    main()
