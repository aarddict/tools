# -*- coding: utf-8 -*-
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

from __future__ import with_statement
import functools
import logging
import os
import urlparse
import collections

from itertools import islice
import json

import yaml

from mwlib import uparser, xhtmlwriter, _locale
from mwlib.log import Log
Log.logfile = None

from mwlib import lrucache, expr
expr._cache = lrucache.mt_lrucache(100)

from mwlib.templ.evaluate import Expander
Expander.parsedTemplateCache = lrucache.lrucache(100)

tojson = functools.partial(json.dumps, ensure_ascii=False)

import multiprocessing
from multiprocessing import Pool
from mwlib.cdb.cdbwiki import WikiDB
from mwlib._version import version as mwlib_version
import mwlib.siteinfo

from aardtools.wiki import mwaardhtmlwriter as writer

import re

lic_dir = os.path.join(os.path.dirname(__file__), 'licenses')

known_licenses = {"Creative Commons Attribution-Share Alike 3.0 Unported":
                  os.path.join(lic_dir, "ccasau-3.0.txt"),
                  "GNU Free Documentation License 1.2":
                  os.path.join(lic_dir, "gfdl-1.2.txt")}

wikidb = None
log = logging.getLogger('wiki')

def _create_wikidb(cdbdir, lang, rtl, filters):
    global wikidb
    wikidb = Wiki(cdbdir, lang, rtl, filters)

def _init_process(cdbdir, lang, rtl, filters):
    global log
    log = multiprocessing.get_logger()
    _create_wikidb(cdbdir, lang, rtl, filters)

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


def mkredirect(title, redirect_target):
    meta = {u'r': redirect_target}
    return title, tojson(('', [], meta)), True, None

def convert(title):
    try:
        text = wikidb.reader[title]

        if not text:
            return title, None, False, None

        redirect = wikidb.get_redirect(text)
        if redirect:
            return mkredirect(title, redirect)

        mwobject = uparser.parseString(title=title,
                                       raw=text,
                                       wikidb=wikidb,
                                       lang=wikidb.lang,
                                       magicwords=wikidb.siteinfo['magicwords'])
        xhtmlwriter.preprocess(mwobject)
        text, tags, languagelinks = writer.convert(mwobject, wikidb.rtl, wikidb.filters)

        for item in wikidb.filters.get('REGEX', ()):
            text = item['re'].sub( item['sub'], text )
    except Exception:
        log.exception('Failed to process article %s', title.encode('utf8'))
        raise ConvertError(title)
    else:
        return title, tojson((text.rstrip(), tags)), False, languagelinks


class BadRedirect(ConvertError): pass


def parse_redirect(text, aliases):
    """
    >>> aliases = [u"#PATRZ", u"#PRZEKIERUJ", u"#TAM", u"#REDIRECT"]
    >>> parse_redirect(u'#PATRZ [[Zmora]]', aliases)
    u'Zmora'
    >>> parse_redirect(u'#PATRZ[[Zmora]]', aliases)
    u'Zmora'
    >>> parse_redirect(u'#PRZEKIERUJ [[Uwierzytelnianie]]', aliases)
    u'Uwierzytelnianie'

    >>> parse_redirect('#TAM[[Żuraw samochodowy]]'.decode('utf8'), aliases)
    u'\u017buraw samochodowy'

    >>> parse_redirect('#перенапр[[абв]]'.decode('utf8'), [u"#\u043f\u0435\u0440\u0435\u043d\u0430\u043f\u0440"])
    u'\u0430\u0431\u0432'

    >>> parse_redirect('#Перенапр[[абв]]'.decode('utf8'),
    ...                [u"#\u043f\u0435\u0440\u0435\u043d\u0430\u043f\u0440",
    ...                 u"#\u043f\u0435\u0440\u0435\u043d\u0430\u043f\u0440".upper()])
    u'\u0430\u0431\u0432'

    >>> parse_redirect(u'abc', aliases)

    >>> parse_redirect(u'#REDIRECT [[abc', aliases)
    Traceback (most recent call last):
    ...
    BadRedirect: ConvertError: [[abc

    >>> parse_redirect(u'#REDIRECT abc', aliases)
    Traceback (most recent call last):
    ...
    BadRedirect: ConvertError: abc

    >>> parse_redirect('#REDIRECT абв'.decode('utf8'), aliases)
    Traceback (most recent call last):
    ...
    BadRedirect: ConvertError: абв

    """
    for alias in aliases:
        if text.startswith(alias) or text.upper().startswith(alias):
            text = text[len(alias):].lstrip()
            begin = text.find('[[')
            if begin < 0:
                raise BadRedirect(text)
            end = text.find(']]')
            if end < 0:
                raise BadRedirect(text)
            return text[begin+2:end]
    return None

class Wiki(WikiDB):

    def __init__(self, cdbdir, lang, rtl, filters):
        WikiDB.__init__(self, cdbdir, lang=lang)
        self.lang = lang
        self.rtl = rtl
        self.redirect_aliases = set()
        aliases = [magicword['aliases']
                                 for magicword in self.siteinfo['magicwords']
                                 if magicword['name'] == 'redirect'][0]

        for alias in aliases:
            self.redirect_aliases.add(alias)
            self.redirect_aliases.add(alias.lower())
            self.redirect_aliases.add(alias.upper())

        self.filters = filters
        raw_exclude_pages_filters = self.filters.get('EXCLUDE_PAGES', ())
        self.exclude_pages_filters = [re.compile(ex, re.UNICODE)
                                      for ex in raw_exclude_pages_filters]


    def get_redirect(self, text):
        redirect = parse_redirect(text, self.redirect_aliases)
        if redirect:
            redirect = self.nshandler.get_fqname(redirect)
        return redirect

    def getURL(self, title):
        return ''

    def getSource(self, title, revision=None):
        from mwlib.metabook import make_source

        g = self.siteinfo['general']
        return make_source(
            name='%s (%s)' % (g['sitename'], g['lang']),
            url=g['base'],
            language=g['lang'],
            base_url=self.nfo['base_url'],
            script_extension=self.nfo['script_extension'],
        )

    def _matches_exclude(self, name):
        return any(fltr.match(name) for fltr in self.exclude_pages_filters)

    def get_page(self,  name,  revision=None):
        if self._matches_exclude(name):
            return
        else:
            return WikiDB.get_page(self, name, revision)

    def normalize_and_get_page(self, name, defaultns):
        fqname = self.nshandler.get_fqname(name, defaultns=defaultns)
        return self.get_page(fqname)

    def normalize_and_get_image_path(self, name):
        assert isinstance(name, basestring)
        name = unicode(name)

        ns, partial, fqname = self.nshandler.splitname(name, defaultns=6)
        if ns != 6:
            return

        if "/" in fqname:
            return None


def load_siteinfo(filename):
    with open(filename) as f:
        siteinfo = json.load(f)
    mwlib.siteinfo.get_siteinfo = lambda lang: siteinfo
    return siteinfo


def load_filters(filename):
    with open(filename) as f:
        print 'Using filters from', filename
        filters = yaml.load(f)

    for filter_section in ['EXCLUDE_PAGES', 'EXCLUDE_CLASSES', 'EXCLUDE_IDS', 'TEXT_REPLACE']:
        filters.setdefault(filter_section, [])

    filters['REGEX'] = []
    text_replace_filters = filters.get('TEXT_REPLACE')
    if text_replace_filters:
        for item in filters['TEXT_REPLACE']:
            sub = ""
            if 'sub' in item:
                sub = item['sub']
            filters['REGEX'].append( { "re": re.compile(item['re']), "sub": sub } )

    return filters

default_description = """ %(title)s for Aard Dictionary is a collection of text documents from %(server)s (articles only). Some documents or portions of documents may have been omited or could not be converted to Aard Dictionary format. All documents can be found online at %(server)s under the same title as displayed in Aard Dictionary.
"""


def fix_server_url(general_siteinfo):
    """
    Get server url from siteinfo's 'general' dict,
    add http if scheme is missing. This will also modify
    given dictionary.

    >>> general_siteinfo = {'server': '//simple.wikipedia.org'}
    >>> fix_server_url(general_siteinfo)
    'http://simple.wikipedia.org'
    >>> general_siteinfo
    {'server': 'http://simple.wikipedia.org'}

    >>> fix_server_url({'server': 'https://en.wikipedia.org'})
    'https://en.wikipedia.org'

    >>> fix_server_url({})
    ''

    """
    server = general_siteinfo.get('server', '')
    if server:
        p = urlparse.urlparse(server)
        if not p.scheme:
            server = urlparse.urlunparse(
                urlparse.ParseResult('http', p.netloc, p.path,
                                     p.params, p.query, p.fragment))
            general_siteinfo['server'] = server
    return server


from aardtools.compiler import ArticleSource, Article


class MediawikiArticleSource(ArticleSource, collections.Sized):

    @classmethod
    def register_argparser(cls, subparsers, parents):

        parser = subparsers.add_parser('wiki', parents=parents)

        parser.add_argument('siteinfo',
                            help=('Path to Mediawiki JSON-formatted site info file. Get it with '
                                  'aard-siteinfo command'))

        parser.add_argument(
            '--processes',
            type=int,
            default=None,
            help=
            'Size of the worker pool (by default equals to the '
            'number of detected CPUs).'
            )

        parser.add_argument(
            '--nomp',
            action='store_true',
            default=False,
            help='Disable multiprocessing, useful for debugging.'
            )

        parser.add_argument( # could be common option, but currently only supported by wiki
            '--start',
            default=0,
            type=int,
            help='Starting article, skip all articles before. Default: %(default)s'
            )

        parser.add_argument( # could be common option, but currently only supported by wiki
            '--end',
            default=None,
            type=int,
            help='End article, stop processing at this article. Default: %(default)s'
            )

        parser.add_argument(
            '--wiki-lang',
            help='Wikipedia language (like en, de, fr). This may be different from actual language '
            'in which articles are written. For example, the value for Simple English Wikipedia  is "simple" '
            '(although the actual articles language is "en"). This is inferred from input file name '
            'if it follows same naming pattern as Wiki XML dumps and starts with "{lang}wiki". '
            'Default: %(default)s'
            )

        parser.add_argument(
            '--lang-links',
            nargs="*",
            help='Add Wikipedia language links to index for these languages '
            '(comma separated list of language codes). Default: %(default)s')

        parser.add_argument( #could be compiler option, but currently support only by wiki
            '--article-count',
            default=0,
            type=int,
            help=('Request specific number of articles, skip redirects '
                  '(if set to a number greater then 0). '
                  'Default: %(default)s'))

        parser.add_argument('--filters',
                          help='JSON-formatted list of filters to apply to data')

        parser.add_argument('--rtl',
                          action="store_true",
                          help='Set direction for Wikipedia articles to rtl')


        parser.set_defaults(article_source_class=cls)


    def make_filers_file_name(self, aname):
        filters_file_name = aname + '.yaml'
        filters_file_name = os.path.join(os.path.dirname(__file__),
                                         'filters', filters_file_name)
        return filters_file_name

    def __init__(self, args):
        super(MediawikiArticleSource, self).__init__(self)
        self.input_file  = os.path.expanduser(args.input_files[0])
        self.filters = {}
        if args.filters:
            if not args.filters.lower().endswith('.yaml'):
                filters_file_name = self.make_filers_file_name(args.filters)
            else:
                filters_file_name = os.path.expanduser(args.filters)
            self.filters = load_filters(filters_file_name)
        else:
            filters_file_name = self.make_filers_file_name(self.input_file.split('-')[0])
            if os.path.exists(filters_file_name):
                self.filters = load_filters(filters_file_name)
        if not self.filters:
            print 'Warning: no article content filters specified'

        self.siteinfo = load_siteinfo(os.path.expanduser(args.siteinfo))
        self.wiki_parser = WikiParser(args, self.filters, self.siteinfo)
        self.start = args.start
        self.end = args.end

    @property
    def metadata(self):
        return self.wiki_parser.metadata

    def __len__(self):
        if self.wiki_parser.requested_article_count:
            return self.wiki_parser.requested_article_count
        w = Wiki(self.input_file, self.wiki_parser.lang,
                 self.wiki_parser.rtl, self.filters)
        for i,a in enumerate(islice(w.articles(), self.start, self.end)):
            pass
        try:
            return i+1
        except:
            return 0

    def __iter__(self):
        return self.parse(self.input_file)

    def parse(self, f):
        for article in self.wiki_parser.parse(f):
            yield article


class WikiParser():

    def __init__(self, options, filters, siteinfo):
        wiki_lang = options.wiki_lang
        self.filters = filters
        self.metadata = {}
        self.metadata['siteinfo'] = siteinfo

        general_siteinfo = siteinfo['general']
        sitename = general_siteinfo['sitename']
        sitelang = general_siteinfo['lang']

        try:
            _locale.set_locale_from_lang(sitelang.encode('latin-1'))
        except BaseException, err:
            print "Error: could not set locale", err
            print "Class: ", sitelang.__class__

        from ConfigParser import ConfigParser
        c = ConfigParser()

        if options.metadata:
            read_metadata_files = c.read(options.metadata)
            if not read_metadata_files:
                log.warn('Metadata file could not be read %s' % options.metadata)
            else:
                log.info('Using metadata from %s', ', '.join(read_metadata_files))
                for opt in c.options('metadata'):
                    value = c.get('metadata', opt)
                    self.metadata[opt] = value
        else:
            log.warn('No metadata file specified')


        if options.license:
            license_file = options.license
        else:
            rights = general_siteinfo['rights']
            if rights in known_licenses:
                license_file = known_licenses[rights]
            else:
                license_file = None
                self.metadata['license'] = rights

        if license_file:
            with open(license_file) as f:
                log.info('Using license text from %s', license_file)
                license_text = f.read()
                self.metadata['license'] = license_text

        if options.copyright:
            copyright_file = options.copyright
            with open(copyright_file) as f:
                log.info('Using copyright text from %s', copyright_file)
                copyright_text = f.read()
                self.metadata['copyright'] = copyright_text

        self.metadata["title"] = sitename
        if options.dict_ver:
            self.metadata["version"] = "-".join((options.dict_ver,
                                                 options.dict_update))

        server = fix_server_url(general_siteinfo)

        self.metadata["source"] = server
        self.metadata["description"] = default_description % dict(server=server,
                                                                  title=sitename)

        self.lang = wiki_lang
        self.rtl = options.rtl
        self.metadata["lang"] = wiki_lang
        self.metadata["sitelang"] =  sitelang
        self.metadata["index_language"] = sitelang
        self.metadata["article_language"] = sitelang
        log.info('Language: %s (%s)', self.lang, sitelang)

        self.metadata['mwlib'] = '.'.join(str(v) for v in mwlib_version)
        self.processes = options.processes if options.processes else None
        self.pool = None
        self.start = options.start
        self.end = options.end
        if options.nomp:
            log.info('Disabling multiprocessing')
            self.parse = self.parse_simple
        else:
            self.parse = self.parse_mp

        if options.lang_links:
            self.lang_links_langs = frozenset(l.strip().lower()
                                              for l in options.lang_links
                                              if l.strip().lower() != sitelang)
            self.metadata["language_links"] = list(self.lang_links_langs)
        else:
            self.lang_links_langs = frozenset()

        self.requested_article_count = options.article_count


    def articles(self, cdbdir):
        if self.start > 0:
            log.info('Skipping to article %d', self.start)
        _create_wikidb(cdbdir, self.lang, self.rtl, self.filters)
        for title in islice(wikidb.articles(), self.start, self.end):
            log.debug('Yielding "%s" for processing', title.encode('utf8'))
            yield title

    def parse_simple(self, cdbdir):
        _init_process(cdbdir, self.lang, self.rtl, self.filters)
        articles = self.articles(cdbdir)
        for a in articles:
            try:
                result = convert(a)
                title, serialized, redirect, langugagelinks = result
                yield Article(title, serialized, isredirect=redirect)
                for item in self.process_languagelinks(title, langugagelinks):
                    yield item
            except ConvertError as e:
                yield Article(e.title, None, failed=True)


    def parse_mp(self, cdbdir):
        try:
            articles = self.articles(cdbdir)
            self.pool = Pool(processes=self.processes,
                             initializer=_init_process,
                             initargs=[cdbdir, self.lang, self.rtl, self.filters],
                             maxtasksperchild=100000)
            real_article_count = 0
            resulti = self.pool.imap_unordered(convert, articles)
            while True:
                try:
                    result = resulti.next()
                    title, serialized, redirect, langugagelinks  = result
                    if not redirect or not self.requested_article_count:
                        real_article_count += 1
                        yield Article(title, serialized, isredirect=redirect)
                        for item in self.process_languagelinks(title, langugagelinks):
                            yield item
                        if (self.requested_article_count and
                            real_article_count >= self.requested_article_count):
                            break
                except ConvertError as e:
                    yield Article(e.title, None, failed=True)
        except:
            log.exception('')
            raise
        finally:
            self.pool.terminate()

    def process_languagelinks(self, title, languagelinks):
        if not languagelinks:
            return
        targets = set()
        for namespace, target in languagelinks:
            if namespace in self.lang_links_langs:
                log.debug('Language link for %s: %s (%s)',
                          title.encode('utf8'), target.encode('utf8'),
                          namespace.encode('utf8'))
                i = target.find(namespace+u':')
                if i > -1:
                    unqualified_target = target[len(namespace)+1:]
                    try:
                        wikidb.reader[unqualified_target]
                    except KeyError:
                        targets.add(unqualified_target)
                else:
                    log.warn('Invalid language link "%s"', target.encode('utf8'))
        for target in targets:
            (l_title, l_serialized,
             _redirect, _langugagelinks) = mkredirect(
                wikidb.nshandler.get_fqname(target), title)
            yield Article(l_title, l_serialized,
                                      isredirect=True, counted=False)

