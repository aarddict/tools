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
from copy import deepcopy

try:
    from xml.etree import cElementTree as etree
except ImportError:
    logging.warning('cElementTree is not available, will use ElementTree')
    from xml.etree import ElementTree as etree

try:
    import json
except ImportError:
    import simplejson as json

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


tojson = functools.partial(json.dumps, ensure_ascii=False)


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
    p = XDXFParser(compiler, options)
    p.parse(input_file)


xdxf_visual_tags = frozenset(('ar',
                              'k',
                              'opt',
                              'nu',
                              'def',
                              'pos',
                              'tense',
                              'tr',
                              'dtrn',
                              'kref',
                              'rref',
                              'iref',
                              'abr',
                              'c',
                              'ex',
                              'co',
                              'su'))


class XDXFParser():

    def _tag_handler_ar(self, e, **_):
        e.set('class', e.tag)
        e.tag = 'div'

    def _tag_handler_c(self, child, **_):
        child.tag = 'span'
        color = child.get('c', '')
        child.attrib.clear()
        child.set('style', 'color: %s;' % color)

    def _tag_handler_iref(self, child, **_):
        child.tag = 'a'

    def _tag_handler_kref(self, child, **_):
        child.tag = 'a'
        child.set('href', child.text)

    def _tag_handler_su(self, child, **_):
        child.tag = 'div'
        child.set('class', 'su')

    def _tag_handler_def(self, child, **_):
        child.tag = 'blockquote'

    def _tag_handler_abr(self, child, **kw):
        abbreviations = kw['abbreviations']
        child.tag = 'abbr'
        abr = child.text
        if abr in abbreviations:
            child.set('title', abbreviations[abr])

    def default_tag_handler(self, child, **_):
        if child.tag in xdxf_visual_tags:
            child.set('class', child.tag)
            child.tag = 'span'

    def __init__(self, consumer, options):
        self.consumer = consumer
        self.options = options

    def _mkabbrs(self, element):
        abbrs = {}
        for abrdef in element:
            if abrdef.tag.lower() == 'abr_def':
                value = abrdef.find('v')
                if value:
                    value_txt = value.text
                    for key in abrdef.findall('k'):
                        abbrs[key.text] = value_txt
        return abbrs

    def _transform_element(self, element, abbreviations):
        handler = getattr(self, '_tag_handler_'+element.tag.lower(), self.default_tag_handler)
        handler(element, abbreviations=abbreviations)


    def _text(self, xdxf_element, abbreviations):
        element = deepcopy(xdxf_element)
        if self.options.skip_article_title:
            tail = ''
            for k in list(element.findall('k')):
                if k.tail:
                    tail += k.tail
                element.remove(k)
            tail = tail.lstrip()
            element.text = tail + element.text if element.text else tail
        self._transform_element(element, abbreviations)
        for child in element.getiterator():
            self._transform_element(child, abbreviations)
        return etree.tostring(element, encoding='utf8')

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
        self.consumer.add_metadata('article_format', 'html')
        abbreviations = {}
        for _, element in etree.iterparse(f):
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

            if element.tag == 'abbreviations':
                abbreviations = self._mkabbrs(element)

            if element.tag == 'ar':
                txt = self._text(element, abbreviations)
                txt = txt.replace('\n', '<br/>')
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
                    serialized = tojson((txt, [], {}))
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
