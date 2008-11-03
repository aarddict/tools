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

tojson = functools.partial(simplejson.dumps,encoding='utf-8', ensure_ascii=False) 

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

    return parser

class Compiler(object):
    
    def __init__(self, output_file_name):
        self.output_file_name = output_file_name
        log.info('Compiling to %s', output_file_name)
        self.article_file_len = 0
        self.article_count = 0
        self.index_count = 0
        self.current_article_pointer = 0
        self.sortex = SortExternal()
        self.article_file =  tempfile.NamedTemporaryFile()
        self.tempDir = tempfile.mkdtemp()
        self.indexDbFullname = os.path.join(self.tempDir, "index.db")
        self.indexDb = shelve.open(self.indexDbFullname, 'n')
        self.metadata = {}
            
    def collect_article(self, title, text, tags):        
        if (not title) or (not text):
            log.debug('Skipped blank article: "%s" -> "%s"', title, text)
            return
        
        jsonstring = compress(tojson([text, tags]))
        collationKeyString4 = collator4.getCollationKey(title).getByteArray()
    
        if text.startswith("#REDIRECT"):
            redirectTitle = text[10:]
            self.sortex.put(collationKeyString4 + "___" + title + "___" + redirectTitle)
            log.debug("Redirect: %s %s", title, text)
            return
        self.sortex.put(collationKeyString4 + "___" + title + "___")
    
        article_unit = struct.pack(">L", len(jsonstring)) + jsonstring
        article_unit_len = len(article_unit)
            
        self.article_file.write(article_unit)
        self.article_file_len += article_unit_len
    
        if self.indexDb.has_key(title):
            log.debug("Duplicate key: %s" , title)
        else:
            log.debug("Real article: %s", title)
            self.indexDb[title] = (0, self.current_article_pointer)
    
        self.current_article_pointer += article_unit_len
        
        if self.article_count % 100 == 0:
            print_progress(self.article_count)
        self.article_count += 1    
        
    def compile(self):
        self.article_file.flush()
        self.sortex.sort()
        log.info("Writing temporary indexes...")
        index1, index1Length, index2, index2Length = self.make_index()
        self.sortex.cleanup()
        self.indexDb.close()
        os.remove(self.indexDbFullname)
        os.rmdir(self.tempDir)
        self.make_aar(index1, index1Length, index2, index2Length)
        
    def make_index(self):
        index1 = tempfile.NamedTemporaryFile()
        index2 = tempfile.NamedTemporaryFile()
        index1Length = 0    
        index2Length = 0    
        for count, item in enumerate(self.sortex):
            if count % 100 == 0:
                print_progress(count)
            sortkey, title, redirectTitle = item.split("___", 2)
            if redirectTitle:
                log.debug("Redirect: %s %s", repr(title), repr(redirectTitle))
                target = redirectTitle
            else:
                target = title
            try:
                fileno, articlePointer = self.indexDb[target]
                index1Unit = struct.pack('>LLL', index2Length, fileno, articlePointer)
                index1.write(index1Unit)
                index1Length += len(index1Unit)
                index2Unit = struct.pack(">L", len(title)) + title
                index2.write(index2Unit)
                index2Length += len(index2Unit)
                self.index_count += 1
                log.debug("sorted: %s %i %i", title, fileno, articlePointer)
            except KeyError:
                log.warn("Redirect not found: %s %s" ,repr(title), repr(redirectTitle))        
        erase_progress(count)
        index1.flush()
        index2.flush()
        return index1, index1Length, index2, index2Length
    
    def write_header(self, output_file, meta_length, index1Length, index2Length):
        article_offset = spec_len(HEADER_SPEC)+meta_length+index1Length+index2Length
        values = dict(signature='aard',
                      version=1,
                      meta_length=meta_length,
                      index_count=self.index_count,
                      article_count=self.article_count,
                      article_offset=article_offset,
                      index1_item_format='>LLL',
                      key_length_format='>L'
                      )
        for name, fmt in HEADER_SPEC:            
            output_file.write(struct.pack(fmt, values[name]))
    
    def write_meta(self, output_file, metadata):
        output_file.write(metadata)
        
    def write_index1(self, output_file, index1):
        index1.seek(0)
        writeCount = 0
        while True:
            if writeCount % 100 == 0:
                print_progress(writeCount)
            unit = index1.read(12)
            if len(unit) == 0:
                break
            index2ptr, fileno, offset = struct.unpack(">LLL", unit)
            unit = struct.pack(">LLL", index2ptr, fileno, offset) 
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
            if writeCount % 100 == 0:
                print_progress(writeCount)
            unitLengthString = index2.read(4)
            if len(unitLengthString) == 0:
                break
            writeCount += 1
            unitLength = struct.unpack(">L", unitLengthString)[0]
            unit = index2.read(unitLength)
            output_file.write(unitLengthString + unit)
        erase_progress(writeCount)
        log.debug('Wrote %d items to index 2', writeCount)
        index2.close()    
    
    def write_articles(self, output_file):
        self.article_file.seek(0)
        writeCount = 0
        while True:
            if writeCount % 100 == 0:
                print_progress(writeCount)
            unitLengthString = self.article_file.read(4)
            if len(unitLengthString) == 0:
                break
            writeCount += 1
            unitLength = struct.unpack(">L", unitLengthString)[0]
            unit = self.article_file.read(unitLength)
            output_file.write(unitLengthString + unit)
        erase_progress(writeCount)
        self.article_file.close()
                
    def make_aar(self, index1, index1Length, index2, index2Length):
        output_file = open(self.output_file_name, "w+b", 8192)
        metadata = compress(tojson(self.metadata))
        self.write_header(output_file, len(metadata), index1Length, index2Length)
        self.write_meta(output_file, metadata)
        self.write_index1(output_file, index1)
        self.write_index2(output_file, index2)
        self.write_articles(output_file)
        output_file.close()
        log.info("Done.")
        
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
    from mediawikiparser import MediaWikiParser
    collator1 =  Collator.createInstance(root_locale)
    collator1.setStrength(Collator.PRIMARY)  
    from mwlib.cdbwiki import WikiDB
    template_db = WikiDB(options.templates) if options.templates else None
    p = MediaWikiParser(collator1, compiler.metadata, template_db, compiler.collect_article)
    p.parseFile(input_file)    

def compile_xdxf(input_file, options, compiler):
    import xdxf
    p = xdxf.XDXFParser(compiler.metadata, compiler.collect_article)
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
        
    aarFileLengthMax = max_file_size(options)    
    log.info('Maximum file size is %d bytes', aarFileLengthMax)
            
    input_type = args[0]
    input_file = args[1]
    
    output_file_name = make_output_file_name(input_file, options)
    compiler = Compiler(output_file_name)
    make_input, collect_articles = known_types[input_type]
    collect_articles(make_input(input_file), options, compiler)
    compiler.compile()    
    

if __name__ == '__main__':
    main()



