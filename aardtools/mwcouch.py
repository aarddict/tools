# -*- coding: utf-8 -*-
import collections
import functools
import json
import logging
import multiprocessing
import os
import re

from datetime import datetime
from urlparse import urlparse

import couchdb

import lxml.html
import lxml.html.clean

from lxml.cssselect import CSSSelector

from aardtools.compiler import ArticleSource, Article
from aardtools.wiki import tex

tojson = functools.partial(json.dumps, ensure_ascii=False)

CSSSelector = functools.partial(CSSSelector, translator='html')

log = logging.getLogger(__name__)

DEFAULT_DESCRIPTION = """ %(title)s for Aard Dictionary is a collection of text documents from %(server)s (articles only). Some documents or portions of documents may have been omited or could not be converted to Aard Dictionary format. All documents can be found online at %(server)s under the same title as displayed in Aard Dictionary.
"""

mathcmds = ('latex', 'blahtex', 'texvc')

def math_as_datauri(text):
    for cmd in mathcmds:
        try:
            imgurl = 'data:image/png;base64,' + tex.toimg(text, cmd)
        except tex.MathRenderingFailed as e:
            log.warn('Could not render math in %r with %r: %s',
                     text, cmd, e)
        except:
            log.warn('Could not render math in %r with %r',
                     text, cmd, exc_info=1)
        else:
            return imgurl


class ConvertError(Exception):

    def __init__(self, title):
        Exception.__init__(self, title)
        self.title = title

    def __str__(self):
        """
        >>> e = ConvertError('абвгд'.decode('utf8'))
        >>> print str(e)
        ConvertError: абвгд

        """
        return 'ConvertError: %s' % self.title.encode('utf8')

    def __repr__(self):
        """
        >>> e = ConvertError('абвгд'.decode('utf8'))
        >>> print repr(e)
        ConvertError: u'\u0430\u0431\u0432\u0433\u0434'

        """
        return 'ConvertError: %r' % self.title


def mkcouch(couch_url):
    parsed_url = urlparse(couch_url)
    couch_db = parsed_url.path.lstrip('/')
    server_url = parsed_url.scheme + '://'+ parsed_url.netloc
    server = couchdb.Server(server_url)
    print "Server:", server.resource.url
    print "Database:", couch_db
    return server[couch_db], server['siteinfo']


SELECTORS = []

def process_initializer(css_selectors):
    for css_selector in css_selectors:
        SELECTORS.append(CSSSelector(css_selector))


class CouchArticleSource(ArticleSource, collections.Sized):

    def __init__(self, args):
        super(CouchArticleSource, self).__init__(self)
        self.couch, siteinfo_couch = mkcouch(args.input_files[0])
        self.startkey = args.startkey
        self.endkey = args.endkey
        self.key = args.key
        self.key_file = args.key_file

        self.filters = []

        if args.filter_file:
            for name in args.filter_file:
                with open(os.path.expanduser(name)) as f:
                    for selector in f:
                        selector = selector.strip()
                        if selector:
                            self.filters.append(selector)

        if args.filter:
            for selector in args.filter:
                self.filters.append(CSSSelector(selector))

        log.info('Will apply following filters:\n%s', '\n'.join(self.filters))

        self._metadata = {}
        self._metadata['siteinfo'] = siteinfo = siteinfo_couch[self.couch.name]

        general_siteinfo = siteinfo['general']
        sitename = general_siteinfo['sitename']
        sitelang = general_siteinfo['lang']
        rightsinfo = siteinfo['rightsinfo']
        self.rtl = 'rtl' in general_siteinfo
        self._metadata['title'] = sitename
        self._metadata['version'] = datetime.now().isoformat().split('T')[0]

        server = general_siteinfo.get('server', '')

        self._metadata['source'] = server
        self._metadata['description'] = (DEFAULT_DESCRIPTION %
                                        dict(server=server, title=sitename))
        self._metadata['lang'] = sitelang
        self._metadata['sitelang'] = sitelang
        self._metadata['license'] = rightsinfo['text']


    @classmethod
    def name(cls):
        return 'mwcouch'

    @classmethod
    def register_args(cls, parser):
        parser.add_argument(
            '-s', '--startkey',
            help='Skip articles with titles before this one when sorted')
        parser.add_argument(
            '-e', '--endkey',
            help='Stop processing when this title is reached')

        parser.add_argument(
            '-k', '--key', nargs="+",
            help='Process specified keys only')

        parser.add_argument(
            '-K', '--key-file',
            help='Process only keys specified in file')

        parser.add_argument(
            '-f', '--filter-file', nargs='+',
            help=('Name of filter file. Filter file consists of '
                  'CSS selectors (see BeautifulSoup documentation '
                  'for description of supported selectors), '
                  'one selector per line. '))

        parser.add_argument(
            '-F', '--filter', nargs='+',
            help=('CSS selectors for elements to exclude '
                  '(see BeautifulSoup documentation '
                  'for description of supported selectors)'))


    @property
    def metadata(self):
        return self._metadata

    def __len__(self):
        if self.key:
            return len(self.key)
        if self.key_file:
            with open(os.path.expanduser(self.key_file)) as f:
                return sum(1 for line in f if line)
        return self.couch.info()['doc_count']

    @property
    def len_includes_redirects(self):
        return False

    def __iter__(self):
        view_args = {
            'stale': 'ok',
            'include_docs': True
        }
        if self.startkey:
            view_args['startkey'] = self.startkey
        if self.endkey:
            view_args['endkey'] = self.endkey
        if self.key:
            view_args['keys'] = self.key

        if self.key_file:
            def articles():
                with open(os.path.expanduser(self.key_file)) as f:
                    for line in f:
                        if line:
                            key = line.strip().decode('utf8').replace('_', ' ')
                            doc = self.couch.get(key)
                            if doc:
                                result = (doc.id, set(doc.get('aliases', ())),
                                          doc['parse']['text']['*'], self.rtl)
                            else:
                                result = key, None, None, False
                            yield result
        else:
            def articles():
                all_docs = self.couch.iterview('_all_docs', 10,
                                               **view_args)
                for row in all_docs:
                    if row and row.doc:
                        try:
                            result = (row.id, set(row.doc.get('aliases', ())),
                                      row.doc['parse']['text']['*'], self.rtl)
                        except Exception:
                            result = row.id, None, None, False
                        yield result

        pool = multiprocessing.Pool(None, process_initializer, [self.filters])
        try:
            resulti = pool.imap_unordered(clean_and_handle_errors, articles())
            while True:
                try:
                    title, aliases, text = resulti.next()
                except ConvertError as cerr:
                    yield Article(cerr.title, '', failed=True)
                else:
                    serialized = tojson((text, [])) if text else None
                    yield Article(title, serialized, isredirect=False)
                    if aliases:
                        for name in aliases:
                            serialized = tojson(('', [], {u'r': title}))
                            yield Article(name, serialized, isredirect=True)
        except:
            log.exception('')
            raise
        finally:
            pool.terminate()


def clean_and_handle_errors((title, aliases, text, rtl)):
    try:
        if text is None:
            return title, aliases, u''
        return title, aliases, cleanup(text, rtl=rtl)
    except KeyboardInterrupt:
        raise
    except Exception:
        log.exception('Failed to convert %r', title)
        raise ConvertError(title)


NEWLINE_RE = re.compile(r'[\n]{2,}')

SEL_IMG_TEX = CSSSelector('img.tex')
SEL_A_NEW = CSSSelector('a.new')
SEL_A_HREF_WIKI = CSSSelector('a[href^="/wiki/"]')
SEL_A_HREF_NO_PROTO = CSSSelector('a[href^="//"]')
SEL_IMG_SRC_NO_PROTO = CSSSelector('img[src^="//"]')
SEL_A_HREF_CITE = CSSSelector('a[href^="#cite"]')
SEL_A_IMAGE = CSSSelector('a.image')

CLEANER = lxml.html.clean.Cleaner(
    comments=True,
    scripts=True,
    javascript=True,
    style=False,
    links=False,
    meta=True,
    processing_instructions=True,
    embedded=True,
    page_structure=True,
    safe_attrs_only=False)


def cleanup(text, rtl=False):

    text = NEWLINE_RE.sub('\n', text)
    doc = lxml.html.fromstring(text)

    CLEANER(doc)

    for selector in SELECTORS:
        for item in selector(doc):
            item.drop_tree()

    for item in SEL_IMG_TEX(doc):
        item.attrib.pop('srcset', None)
        equation = item.attrib.pop('alt', None)
        if equation:
            data_uri = math_as_datauri(equation)
            if data_uri:
                item.attrib['src'] = data_uri

    for item in SEL_A_IMAGE(doc):
        item.drop_tag()

    for item in SEL_A_NEW(doc):
        item.attrib.pop('href', None)

    for item in SEL_A_HREF_WIKI(doc):
        item.attrib['href'] = item.attrib['href'].replace('/wiki/', '')

    for item in SEL_A_HREF_NO_PROTO(doc):
        item.attrib['href'] = 'http:' + item.attrib['href']

    for item in SEL_IMG_SRC_NO_PROTO(doc):
        item.attrib['src'] = 'http:' + item.attrib['src']
        if 'srcset' in item.attrib:
            item.attrib['srcset'] = item.attrib['srcset'].replace('//', 'http://')

    for item in SEL_A_HREF_CITE(doc):
        item.attrib['onclick'] = 'return s("%s")' % item.attrib['href'][1:]

    result = lxml.html.tostring(doc)

    if rtl:
        result = '<div dir="rtl" class="rtl">%s</div>' % result

    return result
