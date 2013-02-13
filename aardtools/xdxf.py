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
# Copyright (C) 2008-2013  Igor Tkach

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

import json

from itertools import combinations


tojson = functools.partial(json.dumps, ensure_ascii=False)

import collections
from aardtools.compiler import ArticleSource, Article


class XdxfArticleSource(ArticleSource, collections.Sized):

    @classmethod
    def register_argparser(cls, subparsers, parents):

        parser = subparsers.add_parser('xdxf', parents=parents)

        parser.add_argument(
            '--skip-article-title',
            action='store_true',
            help=('Do not include article key in rendered article: '
                  'some XDXF dictionaries already inlude title in article text and '
                  'needs this to avoid title duplication'))

        parser.set_defaults(article_source_class=cls)

    def __init__(self, args):
        super(XdxfArticleSource, self).__init__(self)
        self.input_file = args.input_files[0]
        self.xdxf_parser = XDXFParser(args)

    @property
    def metadata(self):
        return self.xdxf_parser.metadata

    def __len__(self):
        count = 0
        f = make_input(self.input_file)
        try:
            for _event, element in etree.iterparse(f):
                if element.tag == 'ar':
                    keys = element.findall('k')
                    for key_element in keys:
                        n_opts = len([c for c in key_element if c.tag == 'opt'])
                        if n_opts:
                            for j in range(n_opts+1):
                                for _comb in combinations(range(n_opts), j):
                                    count += 1
                        else:
                            count += 1
                if element.tag != 'k':
                    element.clear()
        finally:
            f.close()
        return count

    def __iter__(self):
        return self.xdxf_parser.parse(self.input_file)


def make_input(input_file_name):
    if input_file_name == '-':
        return sys.stdin
    input_file_name = os.path.expanduser(input_file_name)
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

    def __init__(self, options):
        self.options = options
        self.metadata = {}

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
        abbreviations = {}
        for _, element in etree.iterparse(f):
            if element.tag == 'description':
                self.metadata[element.tag] = element.text
                element.clear()

            if element.tag == 'full_name':
                self.metadata['title'] = element.text
                element.clear()

            if element.tag == 'xdxf':
                self.metadata['article_language'] = element.get('lang_to')
                self.metadata['index_language'] = element.get('lang_from')
                self.metadata['xdxf_format'] = element.get('format')
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
                    yield Article(first_title, serialized)
                    titles = titles[1:]
                    if titles:
                        for title in titles:
                            logging.debug('Redirect %s ==> %s',
                                          title.encode('utf8'),
                                          first_title.encode('utf8'))
                            meta = {u'r': first_title}
                            serialized = tojson(('', [], meta))
                            yield Article(title, serialized, isredirect=True)
                else:
                    logging.warn('No title found in article:\n%s',
                                 etree.tostring(element, encoding='utf8'))
                element.clear()
