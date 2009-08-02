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

try:
    from itertools import combinations
except ImportError:    
    def combinations(iterable, r):
        # combinations('ABCD', 2) --> AB AC AD BC BD CD
        # combinations(range(4), 3) --> 012 013 023 123
        pool = tuple(iterable)
        n = len(pool)
        if r > n:
            return
        indices = range(r)
        yield tuple(pool[i] for i in indices)
        while True:
            for i in reversed(range(r)):
                if indices[i] != i + n - r:
                    break
            else:
                return
            indices[i] += 1
            for j in range(i+1, r):
                indices[j] = indices[j-1] + 1
            yield tuple(pool[i] for i in indices)
    globals()['combinations'] = combinations


tojson = functools.partial(simplejson.dumps, ensure_ascii=False)


def total(inputfile, options):
    count = 0
    for event, element in etree.iterparse(inputfile):
        if element.tag == 'ar':
            keys = element.findall('k')
            for key_element in keys:
                n_opts = len([c for c in key_element if c.tag == 'opt'])
                if n_opts:
                    for j in range(n_opts+1):
                        for comb in combinations(range(n_opts), j):
                            count += 1
                else:
                    count += 1
        if element.tag != 'k':
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

    def _mktitle(self, title_element, include_opts=()):
        title = title_element.text
        opt_i = -1
        for c in title_element:
            if c.tag == 'nu' and c.tail:
                if title:
                    title += c.tail
                else:
                    title = c.tail
            if c.tag == 'opt':
                opt_i += 1
                if opt_i in include_opts:
                    if title:
                        title += c.text
                    else:
                        title = c.text
                if c.tail:
                    if title:
                        title += c.tail
                    else:
                        title = c.tail
        return title

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

                titles = []
                for title_element in element.findall('k'):
                    n_opts = len([c for c in title_element if c.tag == 'opt'])
                    if n_opts:
                        for j in range(n_opts+1):
                            for comb in combinations(range(n_opts), j):
                                titles.append(self._mktitle(title_element, comb))
                    else:
                        titles.append(self._mktitle(title_element))

                if titles:
                    first_title = titles[0]
                    serialized = tojson((txt, tags, {}))
                    self.consumer.add_article(first_title, serialized,
                                              redirect=False)
                    titles = titles[1:]
                    if titles:
                        for title in titles:
                            logging.debug('Redirect %s ==> %s',
                                          title.encode('utf8'),
                                          first_title.encode('utf8'))
                            meta = {u'r': first_title}
                            serialized = tojson(('', [], meta))
                            self.consumer.add_article(title, serialized,
                                                      redirect=True)
                else:
                    logging.warn('No title found in article:\n%s',
                                 etree.tostring(element, encoding='utf8'))
                element.clear()
