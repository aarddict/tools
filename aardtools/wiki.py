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
# Copyright (C) 2008-2009  Igor Tkach

from __future__ import with_statement
import functools
import re
import logging
import os
import sys
from itertools import islice

import simplejson

from mwlib import uparser, xhtmlwriter
from mwlib.log import Log
Log.logfile = None

from mwlib import lrucache, expr
expr._cache = lrucache.mt_lrucache(100)

from mwlib.templ.evaluate import Expander
Expander.parsedTemplateCache = lrucache.lrucache(100)

import mwaardwriter

tojson = functools.partial(simplejson.dumps, ensure_ascii=False)

import multiprocessing
from multiprocessing import Pool, TimeoutError
from mwlib.cdbwiki import WikiDB, normname
from mwlib._version import version as mwlib_version
from mwlib.siteinfo import get_siteinfo

import gc

wikidb = None
log = logging.getLogger('wiki')

def _create_wikidb(cdbdir, lang):
    global wikidb
    wikidb = Wiki(cdbdir, lang)

def _init_process(cdbdir, lang):
    global log
    log = multiprocessing.get_logger()
    _create_wikidb(cdbdir, lang)

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


class EmptyArticleError(ConvertError): pass

def mkredirect(title, target):
    redirect = normname(target)
    meta = {u'r': redirect}
    return title, tojson(('', [], meta)), True, None

def convert(title):
    gc.collect()
    try:
        text = wikidb.getRawArticle(title, resolveRedirect=False)

        if not text:
            raise EmptyArticleError(title)

        redirect = wikidb.get_redirect(text)
        if redirect:
            return mkredirect(title, redirect)

        mwobject = uparser.parseString(title=title,
                                       raw=text,
                                       wikidb=wikidb,
                                       lang=wikidb.lang)
        xhtmlwriter.preprocess(mwobject)
        text, tags, languagelinks = mwaardwriter.convert(mwobject)
    except EmptyArticleError:
        raise
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

    def __init__(self, cdbdir, lang):
        WikiDB.__init__(self, cdbdir)
        self.lang = lang
        self.siteinfo = get_siteinfo(self.lang)
        self.redirect_aliases = set()
        aliases = [magicword['aliases']
                                 for magicword in self.siteinfo['magicwords']
                                 if magicword['name'] == 'redirect'][0]

        for alias in aliases:
            self.redirect_aliases.add(alias)
            self.redirect_aliases.add(alias.lower())
            self.redirect_aliases.add(alias.upper())


    def get_siteinfo(self):
        return self.siteinfo

    def get_redirect(self, text):
        return parse_redirect(text, self.redirect_aliases)

    def getTemplate(self, title, followRedirects=True):
        if ":" in title:
            title = title.split(':', 1)[1]
        try:
            res = self.reader["Template:"+title]
        except KeyError:
            title = normname(title)
            try:
                res = self.reader["Template:"+title]
            except KeyError:
                return ''

        redirect = parse_redirect(res, self.redirect_aliases)
        if redirect:
            redirect = redirect.split("|", 1)[0].split("#", 1)[0]
            if followRedirects:
                return self.getTemplate(redirect, followRedirects=followRedirects)
            else:
                log.warn('Template redirect not followed: %r -> %r' % (title, redirect))
        return res


def total(inputfile, options):
    w = WikiDB(inputfile)
    for i, a in enumerate(islice(w.articles(), options.start, options.end)):
        pass
    try:
        return i+1
    except:
        return 0


def make_input(input_file_name):
    return input_file_name

def collect_articles(input_file, options, compiler):
    p = WikiParser(options, compiler)
    p.parse(input_file)

default_lic_fname = 'license.txt'
default_copyright_fname = 'copyright.txt'
default_metadata_fname = 'metadata.ini'

class WikiParser():

    def __init__(self, options, consumer):
        self.consumer = consumer

        wiki_lang = options.wiki_lang
        metadata_dir = os.path.join(sys.prefix,'share/aardtools/wiki/%s' % wiki_lang)
        default_metadata_dir = os.path.join(sys.prefix,'share/aardtools/wiki/%s' % 'en')

        try:
            siteinfo = get_siteinfo(wiki_lang)
            if siteinfo is None:
                raise Exception('No site info found for %s' % wiki_lang)
        except:
            log.fatal('Failed to read siteinfo for language %(lang)s, '
                      'can\'t proceed. '
                      'Check that siteinfo-%(lang)s.json exists in <MWLIB HOME>/mwlib/siteinfo, '
                      'run "fetch_siteinfo.py %(lang)s" if not', dict(lang=wiki_lang))
            raise SystemExit(1)
        consumer.add_metadata('siteinfo', siteinfo)
        sitename = siteinfo['general']['sitename']
        sitelang = siteinfo['general']['lang']

        metadata_files = []
        if options.metadata:
            metadata_files.append(options.metadata)
        else:
            metadata_files.append(os.path.join(default_metadata_dir, default_metadata_fname))
            metadata_files.append(os.path.join(metadata_dir, default_metadata_fname))

        from ConfigParser import ConfigParser
        c = ConfigParser(defaults={'ver': options.dict_ver,
                                   'lang': wiki_lang,
                                   'update': options.dict_update,
                                   'name': sitename,
                                   'sitelang': sitelang})
        read_metadata_files = c.read(metadata_files)
        if not read_metadata_files:
            log.warn('No metadata files read.')
        else:
            log.info('Using metadata from %s', ', '.join(read_metadata_files))
        for opt in c.options('metadata'):
            value = c.get('metadata', opt)
            self.consumer.add_metadata(opt, value)

        if not options.license and 'license' not in self.consumer.metadata:
            license_file = os.path.join(metadata_dir, default_lic_fname)
            log.info('Looking for license text in %s', license_file)
            if not os.path.exists(license_file):
                log.info('File %s doesn\'t exist', license_file)
                license_file = os.path.join(default_metadata_dir, default_lic_fname)
                log.info('Looking for license text in %s', license_file)
            try:
                with open(license_file) as f:
                    license_text = f.read()
                    self.consumer.add_metadata('license', license_text)
                    log.info('Using license text from %s', license_file)
            except IOError, e:
                log.warn('No license text will be written to the '
                         'output dictionary: %s', str(e))

        if not options.copyright and 'copyright' not in self.consumer.metadata:
            copyright_file = os.path.join(metadata_dir, default_copyright_fname)
            log.info('Looking for copyright notice text in %s', copyright_file)
            if not os.path.exists(copyright_file):
                log.info('File %s doesn\'t exist', copyright_file)
                copyright_file = os.path.join(default_metadata_dir, default_copyright_fname)
                log.info('Looking for copyright notice text in %s', copyright_file)
            try:
                with open(copyright_file) as f:
                    copyright_text = f.read()
                    self.consumer.add_metadata('copyright', copyright_text)
                    log.info('Using copyright notice text from %s', copyright_file)
            except IOError, e:
                log.warn('No copyright notice text will be written to the '
                         'output dictionary: %s', str(e))


        self.lang = wiki_lang
        self.consumer.add_metadata("index_language", sitelang)
        self.consumer.add_metadata("article_language", sitelang)
        log.info('Language: %s (%s)', self.lang, sitelang)

        self.consumer.add_metadata('mwlib',
                                   '.'.join(str(v) for v in mwlib_version))
        self.special_article_re = re.compile(r'^\w+:\S', re.UNICODE)
        self.processes = options.processes if options.processes else None
        self.pool = None
        self.timeout = options.timeout
        self.timedout_count = 0
        self.start = options.start
        self.end = options.end
        if options.nomp:
            log.info('Disabling multiprocessing')
            self.parse = self.parse_simple
        else:
            self.parse = self.parse_mp
        self.mp_chunk_size = options.mp_chunk_size

        if options.lang_links:
            self.lang_links_langs = set(l.strip().lower()
                                        for l in options.lang_links.split(','))
        else:
            self.lang_links_langs = set()

    def articles(self, f):
        if self.start > 0:
            log.info('Skipping to article %d', self.start)
        _create_wikidb(f, self.lang)
        for title in islice(wikidb.articles(), self.start, self.end):
            if self.special_article_re.match(title):
                self.consumer.skip_article(title)
                continue
            log.debug('Yielding "%s" for processing', title.encode('utf8'))
            yield title
            gc.collect()

    def reset_pool(self, cdbdir, terminate=True):
        if self.pool and terminate:
            log.info('Terminating current worker pool')
            self.pool.terminate()
        log.info('Creating new worker pool with wiki cdb at %s', cdbdir)

        self.pool = Pool(processes=self.processes,
                         initializer=_init_process,
                         initargs=[cdbdir, self.lang])

    def parse_simple(self, f):
        self.consumer.add_metadata('article_format', 'json')
        articles = self.articles(f)
        for a in articles:
            try:
                result = convert(a)
                title, serialized, redirect, langugagelinks = result
                self.consumer.add_article(title, serialized, redirect)
                self.process_languagelinks(title, langugagelinks)
            except EmptyArticleError, e:
                self.consumer.empty_article(e.title)
            except ConvertError, e:
                self.consumer.fail_article(e.title)

    def parse_mp(self, f):
        try:
            self.consumer.add_metadata('article_format', 'json')
            articles = self.articles(f)
            self.reset_pool(f)
            iter_count = 1
            while True:
                if iter_count:
                    chunk = islice(articles, self.mp_chunk_size)
                    iter_count = 0
                else:
                    break

                resulti = self.pool.imap_unordered(convert, chunk)
                while True:
                    try:
                        result = resulti.next(self.timeout)
                        iter_count += 1
                        title, serialized, redirect, langugagelinks  = result
                        self.consumer.add_article(title, serialized, redirect)
                        self.process_languagelinks(title, langugagelinks)
                    except StopIteration:
                        break
                    except TimeoutError:
                        log.warn('Worker pool timed out')
                        self.consumer.timedout(count=len(multiprocessing.active_children()))
                        self.reset_pool(f)
                        resulti = self.pool.imap_unordered(convert, chunk)
                    except AssertionError:
                        log.exception()
                    except EmptyArticleError, e:
                        self.consumer.empty_article(e.title)
                    except ConvertError, e:
                        self.consumer.fail_article(e.title)
                    except KeyboardInterrupt:
                        log.error('Keyboard interrupt: '
                                  'terminating worker pool')
                        self.pool.terminate()
                        raise

                self.pool.close()
                self.reset_pool(f, terminate=False)
        finally:
            self.pool.close()
            self.pool.join()

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
                    if wikidb.getRawArticle(unqualified_target, resolveRedirect=False) is None:
                        targets.add(unqualified_target)
                else:
                    log.warn('Invalid language link "%s"', target.encode('utf8'))
        for target in targets:
            l_title, l_serialized, l_redirect, l_langugagelinks = mkredirect(target, title)
            self.consumer.add_article(l_title, l_serialized,
                                      redirect=True, count=False)

