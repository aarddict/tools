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
import aarddict
import logging
import sys 
import bz2
import struct
import os
import tempfile
import shelve
import datetime
import optparse

from PyICU import Locale, Collator

from sortexternal import SortExternal
from aarddict import compactjson

logging.basicConfig(format='%(levelname)s: %(message)s')
log = logging.getLogger()

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

def createArticleFile():
    global header
    global aarFile, aarFileLength
    global options

    if options.output_file[-3:] == "aar":
        extFilenamePrefix = options.output_file[:-2]
    else:
        extFilenamePrefix = options.output_file + ".a"

    aarFile.append(open(extFilenamePrefix + ("%02i" % len(aarFile)), "w+b", 4096))
    aarFileLength.append(0)
    log.debug("New article file: %s" , aarFile[-1].name)
    extHeader = {}
    extHeader["article_offset"] = "%012i" % 0
    extHeader["major_version"] = header["major_version"]
    extHeader["minor_version"] = header["minor_version"]
    extHeader["timestamp"] = header["timestamp"]
    extHeader["file_sequence"] = len(aarFile) - 1
    jsonText = compactjson.dumps(extHeader)
    extHeader["article_offset"] = "%012i" % (5 + 8 + len(jsonText))
    jsonText = compactjson.dumps(extHeader)
    aarFile[-1].write("aar%02i" % header["major_version"])
    aarFileLength[-1] += 5
    aarFile[-1].write("%08i" % len(jsonText))
    aarFileLength[-1] += 8
    aarFile[-1].write(jsonText)
    aarFileLength[-1] += len(jsonText)

def handleArticle(title, text, tags):
        
    global header
    global articlePointer
    global aarFile, aarFileLength
    
    if (not title) or (not text):
        log.debug('Skipped blank article: "%s" -> "%s"', title, text)
        return
    
    jsonstring = compactjson.dumps([text, tags])
    compressed = jsonstring
    for compress in aarddict.compression:
        c = compress(jsonstring)
        if len(c) < len(compressed):
            compressed = c        
    
    jsonstring = compressed
    collationKeyString4 = collator4.getCollationKey(title).getByteArray()

    if text.startswith("#REDIRECT"):
        redirectTitle = text[10:]
        sortex.put(collationKeyString4 + "___" + title + "___" + redirectTitle)
        log.debug("Redirect: %s %s", title, text)
        return
    sortex.put(collationKeyString4 + "___" + title + "___")

    articleUnit = struct.pack(">L", len(jsonstring)) + jsonstring
    articleUnitLength = len(articleUnit)
    if aarFileLength[-1] + articleUnitLength > aarFileLengthMax:
        createArticleFile()
        articlePointer = 0L
        
    aarFile[-1].write(articleUnit)
    aarFileLength[-1] += articleUnitLength

    if indexDb.has_key(title):
        log.debug("Duplicate key: %s" , title)
    else:
        log.debug("Real article: %s", title)
        indexDb[title] = (len(aarFile) - 1, articlePointer)

    articlePointer += articleUnitLength
    
    if header["article_count"] % 100 == 0:
        print_progress(header["article_count"])
    header["article_count"] += 1

def makeFullIndex():
    global aarFile, aarFileLength
    global index1Length, index2Length
    global header
    
    for count, item in enumerate(sortex):
        if count % 100 == 0:
            countstr = str(count)
            sys.stdout.write("\b"*len(countstr) + countstr)
            sys.stdout.flush()
        sortkey, title, redirectTitle = item.split("___", 2)
        if redirectTitle:
            log.debug("Redirect: %s %s", repr(title), repr(redirectTitle))
            target = redirectTitle
        else:
            target = title
        try:
            fileno, articlePointer = indexDb[target]
            index1Unit = struct.pack('>LLL', long(index2Length), long(fileno), long(articlePointer))
            index1.write(index1Unit)
            index1Length += len(index1Unit)
            index2Unit = struct.pack(">L", long(len(title))) + title
            index2.write(index2Unit)
            index2Length += len(index2Unit)
            header["index_count"] += 1
            log.debug("sorted: %s %i %i", title, fileno, articlePointer)
        except KeyError:
            log.warn("Redirect not found: %s %s" ,repr(title), repr(redirectTitle))
    
    sys.stdout.write("\b"*len(countstr))
    sys.stdout.flush()    
    log.info("Sorted %d items", count)

root_locale = Locale('root')
collator4 =  Collator.createInstance(root_locale)
collator4.setStrength(Collator.QUATERNARY)

articlePointer = 0L
aarFile = []
aarFileLength = []
index1Length = 0
index2Length = 0

header = {
    "major_version": 1,
    "minor_version": 0,
    "timestamp": str(datetime.datetime.utcnow()),
    "file_sequence": 0,
    "article_language": "",
    "index_language": ""
    }

def compile_wiki(input_file, options, handle_article):
    from mediawikiparser import MediaWikiParser
    collator1 =  Collator.createInstance(root_locale)
    collator1.setStrength(Collator.PRIMARY)  
    from mwlib.cdbwiki import WikiDB
    template_db = WikiDB(options.templates) if options.templates else None
    p = MediaWikiParser(collator1, header, template_db, handle_article)
    p.parseFile(input_file)    

def compile_xdxf(input_file, options, handle_article):
    import xdxf
    p = xdxf.XDXFParser(header, handle_article)
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
    global options, aarFileLengthMax
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
    
    output_file = make_output_file_name(input_file, options)
    
    log.info('Compiling to %s', output_file)
    
    global sortex, indexDb, index1, index2
    
    tempDir = tempfile.mkdtemp()
    sortex = SortExternal()
                        
    aarFile.append(open(output_file, "w+b", 4096))
    aarFileLength.append(0)
    
    createArticleFile()    
    
    indexDbFullname = os.path.join(tempDir, "index.db")
    indexDb = shelve.open(indexDbFullname, 'n')
        
    index1 = tempfile.NamedTemporaryFile()
    index2 = tempfile.NamedTemporaryFile()
    
    header["article_count"] =  0
    header["index_count"] =  0
    
    make_input, compile = known_types[input_type]
    
    compile(make_input(input_file), options, handleArticle)
    erase_progress(header["article_count"])
    log.info('Article count: %d', header["article_count"])
    log.info("Sorting index...")        
    sortex.sort()
    log.info("Writing temporary indexes...")
    makeFullIndex()
    sortex.cleanup()
    indexDb.close()
    os.remove(indexDbFullname)
    os.rmdir(tempDir)
    
    combineFiles = False
    header["file_count"] = len(aarFile)
    if 100 + index1Length + index2Length + aarFileLength[-1] < aarFileLengthMax:
        header["file_count"] -= 1
        combineFiles = True
    header["file_count"] = "%06i" % header["file_count"]
    
    log.debug("Composing header...")
            
    header["index1_length"] = index1Length
    header["index2_length"] = index2Length
    
    header["index1_offset"] = "%012i" % 0
    header["index2_offset"] = "%012i" % 0
    header["article_offset"] = "%012i" % 0
    
    jsonText = compactjson.dumps(header)
    
    header["index1_offset"] = "%012i" % (5 + 8 + len(jsonText))
    header["index2_offset"] = "%012i" % (5 + 8 + len(jsonText) + index1Length)
    header["article_offset"] = "%012i" % (5 + 8 + len(jsonText) + index1Length + index2Length)
    
    log.debug("Writing header...")
    
    jsonText = compactjson.dumps(header)
    
    aarFile[0].write("aar%02i" % header["major_version"])
    aarFileLength[0] += 5
    
    aarFile[0].write("%08i" % len(jsonText))
    aarFileLength[0] += 8
    
    aarFile[0].write(jsonText)
    aarFileLength[0] += len(jsonText)
    
    log.debug('Writing index 1...')
    
    index1.flush()
    index1.seek(0)
    writeCount = 0
    while 1:
        if writeCount % 100 == 0:
            print_progress(writeCount)
        unit = index1.read(12)
        if len(unit) == 0:
            break
        index2ptr, fileno, offset = struct.unpack(">LLL", unit)
        if combineFiles and fileno == len(aarFile) - 1:
            fileno = 0L
        unit = struct.pack(">LLL", index2ptr, fileno, offset) 
        writeCount += 1
        aarFile[0].write(unit)
        aarFileLength[0] += 12
    erase_progress(writeCount)
    log.debug('Wrote %d items to index 1', writeCount)
    index1.close()
    log.debug('Writing index 2...')    
    index2.flush()
    index2.seek(0)
    writeCount = 0
    while 1:
        if writeCount % 100 == 0:
            print_progress(writeCount)
        unitLengthString = index2.read(4)
        if len(unitLengthString) == 0:
            break
        writeCount += 1
        unitLength = struct.unpack(">L", unitLengthString)[0]
        unit = index2.read(unitLength)
        aarFile[0].write(unitLengthString + unit)
        aarFileLength[0] += 4 + unitLength
    erase_progress(writeCount)
    log.debug('Wrote %d items to index 2', writeCount)
    index2.close()    
    writeCount = 0L
    
    if combineFiles:
        log.debug('Appending %s to %s', aarFile[-1].name, aarFile[0].name)
        aarFile[-1].flush()
        aarFile[-1].seek(0)
        aarFile[-1].read(5)
        headerLength = int(aarFile[-1].read(8))
        aarFile[-1].read(headerLength)
    
        while 1:
            if writeCount % 100 == 0:
                print_progress(writeCount)
            unitLengthString = aarFile[-1].read(4)
            if len(unitLengthString) == 0:
                break
            writeCount += 1
            unitLength = struct.unpack(">L", unitLengthString)[0]
            unit = aarFile[-1].read(unitLength)
            aarFile[0].write(unitLengthString + unit)
            aarFileLength[0] += 4 + unitLength
        erase_progress(writeCount)
        log.debug("Deleting %s", aarFile[-1].name)
        os.remove(aarFile[-1].name)    
        aarFile.pop()
    
    log.info("Created %i output file(s)", len(aarFile))
    
    for f in aarFile:
        f.close
       
    log.info("Done.")

if __name__ == '__main__':
    main()



