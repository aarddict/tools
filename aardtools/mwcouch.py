# -*- coding: utf-8 -*-
import collections
import functools
import itertools
import json
import logging
import os
import multiprocessing

from datetime import datetime
from urlparse import urlparse

import couchdb
from bs4 import BeautifulSoup, Comment

from aardtools.compiler import ArticleSource, Article
from aardtools.wiki import tex

tojson = functools.partial(json.dumps, ensure_ascii=False)

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


class CouchArticleSource(ArticleSource, collections.Sized):

    def __init__(self, args):
        super(CouchArticleSource, self).__init__(self)
        self.couch, siteinfo_couch = mkcouch(args.input_files[0])
        self.startkey = args.startkey
        self.endkey = args.endkey
        self.key = args.key

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
                self.filters.append(selector)

        log.info('Will apply following filters:\n%s', '\n'.join(self.filters))

        self._metadata = {}
        self._metadata['siteinfo'] = siteinfo = siteinfo_couch[self.couch.name]

        general_siteinfo = siteinfo['general']
        sitename = general_siteinfo['sitename']
        sitelang = general_siteinfo['lang']
        rightsinfo = siteinfo['rightsinfo']

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
            '--startkey',
            help='Skip articles with titles before this one when sorted')
        parser.add_argument(
            '--endkey',
            help='Stop processing when this title is reached')

        parser.add_argument(
            '--key', nargs="+",
            help='Process specified keys only')

        parser.add_argument(
            '--filter-file', nargs='+',
            help=('Name of filter file. Filter file consists of '
                  'CSS selectors (see BeautifulSoup documentation '
                  'for description of supported selectors), '
                  'one selector per line. '))

        parser.add_argument(
            '--filter', nargs='+',
            help=('CSS selectors for elements to exclude '
                  '(see BeautifulSoup documentation '
                  'for description of supported selectors)'))


    @property
    def metadata(self):
        return self._metadata

    def __len__(self):
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

        all_docs = self.couch.iterview('_all_docs', 10,
                                       **view_args)
        def articles():
            for row in all_docs:
                if row and row.doc:
                    yield (row.id, set(row.doc.get('aliases', ())),
                           row.doc['parse']['text']['*'], self.filters)
        pool = multiprocessing.Pool()
        try:
            resulti = pool.imap_unordered(clean_and_handle_errors, articles())
            while True:
                try:
                    title, aliases, text = resulti.next()
                except ConvertError as cerr:
                    yield Article(cerr.title, '', failed=True)
                else:
                    serialized = tojson((text, []))
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


def clean_and_handle_errors((title, aliases, text, filters)):
    try:
        return title, aliases, cleanup(text, filters)
    except KeyboardInterrupt:
        raise
    except Exception:
        log.exception('Failed to convert %r', title)
        raise ConvertError(title)


def cleanup(text, filters=()):
    soup = BeautifulSoup(text)

    to_remove = [
        soup(lambda tag:
             tag and tag.name == 'img' and 'tex'
             not in tag.attrs.get('class', ())),
        soup(lambda tag:
             tag and tag.name == 'link' and
             not 'stylesheet' in tag.attrs.get('rel', ())),
        soup(lambda tag:
             tag and tag.name == 'meta' and
             not 'charset' in tag.attrs),
        soup(text=lambda text: isinstance(text, Comment))
    ]

    for selector in filters:
        to_remove.append(soup.select(selector))

    for item in itertools.chain(*to_remove):
        item.extract()

    for item in soup('a', **{'class': 'image'}):
        item.unwrap()

    for item in soup('a', **{'class': 'new'}):
        item.attrs.pop('href', None)

    for item in soup(
            lambda tag:
            tag.name == 'a' and tag.attrs.get('href', '').startswith('/wiki/')):
        item.attrs['href'] = (item.attrs['href']
                              .replace('/wiki/', '').replace('_', ' '))

    for item in soup('img', **{'class': 'tex'}):
        item.attrs.pop('srcset', None)
        eq = item.get('alt')
        if eq:
            data_uri = math_as_datauri(eq)
            if data_uri:
                item['src'] = data_uri

    for item in soup(
            lambda tag:
            tag.name == 'a' and tag.attrs.get('href', '').startswith('//')):
        item.attrs['href'] = 'http:'+item.attrs['href']

    for item in soup('a', href=lambda href: href and href.startswith('#cite_')):
        item['onclick'] = 'return s("%s")' % item['href'][1:]

    for item in soup('a', href=lambda href: href and href.endswith('.ogg')):
        item.unwrap()

    return unicode(soup)
