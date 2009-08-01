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
# Copyright (C) 2008-2009  Igor Tkach

import os
import sys
import logging
import functools

try:
    from xml.etree import cElementTree as etree
except ImportError:
    logging.warning('cElementTree is not available, will use ElementTree')
    from xml.etree import ElementTree as etree
    
import simplejson

tojson = functools.partial(simplejson.dumps, ensure_ascii=False)

def total(inputfile, options):
    count = 0
    for event, element in etree.iterparse(inputfile):
        if element.tag == 'ar':
            count += len(element.findall('k'))
        element.clear()
    return count

def make_input(input_file_name):
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

def collect_articles(input_file, options, compiler):
    p = XDXFParser(compiler)
    p.parse(input_file)

class XDXFParser():

    def __init__(self, consumer):
        self.consumer = consumer

    def _text(self, element, tags, offset=0):
        txt = ''
        start = offset
        if element.text:
            txt += element.text
        for c in element:
            txt += self._text(c, tags, offset + len(txt))
        end = start + len(txt)
        tags.append([element.tag, start, end, dict(element.attrib)])
        if element.tail:
            txt += element.tail
        return txt

    def parse(self, f):
        self.consumer.add_metadata('article_format', 'json')
        for event, element in etree.iterparse(f):
            if element.tag == 'description':
                self.consumer.add_metadata(element.tag, element.text)
                element.clear()

            if element.tag == 'full_name':
                self.consumer.add_metadata('title', element.text)
                element.clear()

            if element.tag == 'xdxf':
                self.consumer.add_metadata('article_language',
                                           element.get('lang_to'))
                self.consumer.add_metadata('index_language',
                                           element.get('lang_from'))
                self.consumer.add_metadata('xdxf_format',
                                           element.get('format'))
                element.clear()

            if element.tag == 'ar':
                tags = []
                txt = self._text(element, tags)
                for i, title_elements in enumerate(element.findall('k')):
                    first_title = None
                    title = title_elements.text
                    try:
                        if i == 0:
                            first_title = title
                            serialized = tojson((txt, tags, {}))
                            self.consumer.add_article(title, serialized,
                                                      redirect=False)
                        else:
                            logging.debug('Redirect %s ==> %s',
                                          title.encode('utf8'),
                                          first_title.encode('utf8'))
                            meta = {u'redirect': first_title}
                            serialized = tojson(('', [], meta))
                            self.consumer.add_article(title, serialized,
                                                      redirect=True)
                    except KeyboardInterrupt:
                        raise
                    except Exception:
                        logging.exception('Failed to convert article %s',
                                          title.encode('utf8'))
                        self.consumer.fail_article(title)
                element.clear()
