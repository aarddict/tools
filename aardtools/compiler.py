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
    sys.stderr.write("New article file: %s\n" % aarFile[-1].name)
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
        #sys.stderr.write("Skipped blank article: \"%s\" -> \"%s\"\n" % (title, text))
        return
    
    jsonstring = compactjson.dumps([text, tags])
    jsonstring = bz2.compress(jsonstring)
    #sys.stderr.write("write article: %i %i %s\n" % (articleTempFile.tell(), len(jsonstring), title))    

    collationKeyString4 = collator4.getCollationKey(title).getByteArray()

    if text.startswith("#REDIRECT"):
        redirectTitle = text[10:]
        sortex.put(collationKeyString4 + "___" + title + "___" + redirectTitle)
        sys.stderr.write("Redirect: %s %s\n" % (title, text))
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
        sys.stderr.write("Duplicate key: %s\n" % title)
    else:
        #sys.stderr.write("Real article: %s\n" % title)
        indexDb[title] = (len(aarFile) - 1, articlePointer)

    articlePointer += articleUnitLength
    
    if header["article_count"] % 100 == 0:
        sys.stderr.write("\r" + str(header["article_count"]))
    header["article_count"] += 1

def makeFullIndex():
    global aarFile, aarFileLength
    global index1Length, index2Length
    global header
    
    count = 0

    for item in sortex:
        if count % 100 == 0:
            sys.stderr.write("\r" + str(count))
        count = count + 1
        sortkey, title, redirectTitle = item.split("___", 2)
        if redirectTitle:
            #sys.stderr.write("Redirect: %s %s\n" % (repr(title), repr(redirectTitle)))
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
            sys.stderr.write("sorted: %s %i %i\n" % (title, fileno, articlePointer))
        except KeyError:
            sys.stderr.write("Redirect not found: %s %s\n" % (repr(title), repr(redirectTitle)))
    
    sys.stderr.write("\r" + str(count) + "\n")

root_locale = Locale('root')
collator4 =  Collator.createInstance(root_locale)
collator4.setStrength(Collator.QUATERNARY)

articlePointer = 0L
aarFile = []
aarFileLength = []
index1Length = 0
index2Length = 0
aarFileLengthMax = 2000000000

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
        
        
def main():
    global options
    opt_parser = make_opt_parser()
    options, args = opt_parser.parse_args()
    
    if not args:
        opt_parser.print_help()
        raise SystemExit()    
    
    if len(args) != 2:
        log.error('Not enough parameters\n') 
        opt_parser.print_help()
        raise SystemExit()    

    if args[0] not in known_types:
        log.error('Unknown input type %s, expected one of %s \n', 
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
    
    if options.output_file:
        output_file = options.output_file
    else:            
        output_file = os.path.basename(input_file)
        output_file = output_file[:output_file.rfind('.')]
        if (output_file.endswith('.tar') or 
            output_file.endswith('.xml') or
            output_file.endswith('.xdxf')):
            output_file = output_file[:output_file.rfind('.')]
        output_file += '.aar' 
    
    log.info('Compiling to %s', output_file)
    
    global sortex, indexDb, index1, index2
    
    tempDir = tempfile.mkdtemp()
    sortex = SortExternal()
                        
    aarFile.append(open(output_file, "w+b", 4096))
    aarFileLength.append(0)
    
    createArticleFile()    
    
    indexDbFullname = os.path.join(tempDir, "index.db")
    indexDb = shelve.open(indexDbFullname, 'n')
    
#    if options.templates:
#        templateDb = cdbwiki.WikiDB(options.templates)
#    else:
#        templateDb = None
        
    index1 = tempfile.NamedTemporaryFile()
    index2 = tempfile.NamedTemporaryFile()
    
    header["article_count"] =  0
    header["index_count"] =  0
    
    make_input, compile = known_types[input_type]
    
    compile(make_input(input_file), options, handleArticle)
    
#    if input_type == "xdxf" or inputFile.name[-5:] == ".xdxf":        
#        sys.stderr.write("Compiling %s as xdxf\n" % inputFile.name)
#        import xdxf
#        p = xdxf.XDXFParser(header, handleArticle)
#        p.parse(inputFile)
#    else:  
#        sys.stderr.write("Compiling %s as mediawiki\n" % inputFile.name)
#        from mediawikiparser import MediaWikiParser
#        collator1 =  Collator.createInstance(root_locale)
#        collator1.setStrength(Collator.PRIMARY)        
#        p = MediaWikiParser(collator1, header, templateDb, handleArticle)
#        p.parseFile(inputFile)
    
    sys.stderr.write("\r" + str(header["article_count"]) + "\n")
    sys.stderr.write("Sorting index...\n")
    sortex.sort()
    sys.stderr.write("Writing temporary indexes...\n")
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
    
    sys.stderr.write("Composing header...\n")
            
    header["index1_length"] = index1Length
    header["index2_length"] = index2Length
    
    header["index1_offset"] = "%012i" % 0
    header["index2_offset"] = "%012i" % 0
    header["article_offset"] = "%012i" % 0
    
    jsonText = compactjson.dumps(header)
    
    header["index1_offset"] = "%012i" % (5 + 8 + len(jsonText))
    header["index2_offset"] = "%012i" % (5 + 8 + len(jsonText) + index1Length)
    header["article_offset"] = "%012i" % (5 + 8 + len(jsonText) + index1Length + index2Length)
    
    sys.stderr.write("Writing header...\n")
    
    jsonText = compactjson.dumps(header)
    
    aarFile[0].write("aar%02i" % header["major_version"])
    aarFileLength[0] += 5
    
    aarFile[0].write("%08i" % len(jsonText))
    aarFileLength[0] += 8
    
    aarFile[0].write(jsonText)
    aarFileLength[0] += len(jsonText)
    
    sys.stderr.write("Writing index 1...\n")
    
    index1.flush()
    index1.seek(0)
    writeCount = 0
    while 1:
        if writeCount % 100 == 0:
            sys.stderr.write("\r" + str(writeCount))
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
    sys.stderr.write("\r" + str(writeCount) + "\n")
    index1.close()
    
    sys.stderr.write("Writing index 2...\n")
    
    index2.flush()
    index2.seek(0)
    writeCount = 0
    while 1:
        if writeCount % 100 == 0:
            sys.stderr.write("\r" + str(writeCount))
        unitLengthString = index2.read(4)
        if len(unitLengthString) == 0:
            break
        writeCount += 1
        unitLength = struct.unpack(">L", unitLengthString)[0]
        unit = index2.read(unitLength)
        aarFile[0].write(unitLengthString + unit)
        aarFileLength[0] += 4 + unitLength
    sys.stderr.write("\r" + str(writeCount) + "\n")
    index2.close()
    
    writeCount = 0L
    
    if combineFiles:
        sys.stderr.write("Appending %s to %s\n" % (aarFile[-1].name, aarFile[0].name))
        aarFile[-1].flush()
        aarFile[-1].seek(0)
        aarFile[-1].read(5)
        headerLength = int(aarFile[-1].read(8))
        aarFile[-1].read(headerLength)
    
        while 1:
            if writeCount % 100 == 0:
                sys.stderr.write("\r" + str(writeCount))
            unitLengthString = aarFile[-1].read(4)
            if len(unitLengthString) == 0:
                break
            writeCount += 1
            unitLength = struct.unpack(">L", unitLengthString)[0]
            unit = aarFile[-1].read(unitLength)
            aarFile[0].write(unitLengthString + unit)
            aarFileLength[0] += 4 + unitLength
        sys.stderr.write("\r" + str(writeCount) + "\n")
        sys.stderr.write("Deleting %s\n" % aarFile[-1].name)
        os.remove(aarFile[-1].name)    
        aarFile.pop()
    
    sys.stderr.write("Created %i output file(s)\n" % len(aarFile))
    for f in aarFile:
        f.close
       
    sys.stderr.write("Done.\n")

if __name__ == '__main__':
    main()



