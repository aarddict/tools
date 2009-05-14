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

import functools
import re
import logging

import simplejson

from mwlib import uparser, xhtmlwriter
from mwlib.log import Log
Log.logfile = None

import mwaardwriter

tojson = functools.partial(simplejson.dumps, ensure_ascii=False)

import multiprocessing
from multiprocessing import Pool, TimeoutError
from mwlib.cdbwiki import WikiDB, normname
from mwlib._version import version as mwlib_version
from mwlib.siteinfo import get_siteinfo

redirect_rex = WikiDB.redirect_rex

wikidb = None
log = logging.getLogger()

def _create_wikidb(cdbdir, lang):
    global wikidb
    wikidb = Wiki(cdbdir, lang)

def _init_process(cdbdir, lang):
    global log
    log = multiprocessing.get_logger()
    _create_wikidb(cdbdir, lang)

def convert(data):
    title, text  = data
    try:
        mwobject = uparser.parseString(title=title,
                                       raw=text,
                                       wikidb=wikidb,
                                       lang=wikidb.lang)
        xhtmlwriter.preprocess(mwobject)
        text, tags = mwaardwriter.convert(mwobject)
    except Exception:
        msg = 'Failed to process article %r' % title
        log.exception(msg)
        raise RuntimeError(msg)
    return title, tojson((text.rstrip(), tags))

class Wiki(WikiDB):

    def __init__(self, cdbdir, lang):
        WikiDB.__init__(self, cdbdir)
        self.lang = lang
        self.siteinfo = get_siteinfo(self.lang)

    def get_siteinfo(self):
        return self.siteinfo

class WikiParser():

    def __init__(self, options, consumer):
        self.consumer = consumer
        self.lang = None
        self._set_lang(options.lang)
        self.consumer.add_metadata('mwlib',
                                   '.'.join(str(v) for v in mwlib_version))
        self.special_article_re = re.compile(r'^\w+:\S', re.UNICODE)
        self.processes = options.processes if options.processes else None
        self.pool = None
        self.active_processes = multiprocessing.active_children()
        self.timeout = options.timeout
        self.timedout_count = 0
        self.error_count = 0
        self.start = options.start
        self.end = options.end
        if options.nomp:
            log.info('Disabling multiprocessing')
            self.parse = self.parse_simple
        else:
            self.parse = self.parse_mp

    def _set_lang(self, lang):
        self.lang = lang
        self.consumer.add_metadata("index_language", lang)
        self.consumer.add_metadata("article_language", lang)
        log.info('Language: %s', self.lang)

    def articles(self, f):
        if self.start > 0:
            log.info('Skipping to article %d', self.start)
        _create_wikidb(f, self.lang)
        skipped_count = 0

        for read_count, title in enumerate(wikidb.articles()):

            if read_count <= self.start:
                if read_count % 10000 == 0:
                    log.info('Skipped %d', read_count)
                continue

            if self.end and read_count > self.end:
                log.info('Reached article %d, stopping.', self.end)
                break

            text = wikidb.getRawArticle(title, resolveRedirect=False)

            if not text:
                continue

            if self.special_article_re.match(title):
                skipped_count += 1
                log.debug('Special article %s, skipping (%d so far)',
                              title.encode('utf8'), skipped_count)
                continue

            mo = redirect_rex.search(text)
            if mo:
                redirect = mo.group('redirect')
                redirect = normname(redirect.split("|", 1)[0].split("#", 1)[0])
                meta = {u'r': redirect}
                self.consumer.add_article(title, tojson(('', [], meta)))
                continue

            log.debug('Yielding "%s" for processing', title.encode('utf8'))

            yield title, text


    def reset_pool(self, cdbdir):
        if self.pool:
            log.info('Terminating current worker pool')
            self.pool.terminate()
        log.info('Creating new worker pool with wiki cdb at %s', cdbdir)

        self.pool = Pool(processes=self.processes,
                         initializer=_init_process,
                         initargs=[cdbdir, self.lang])

    def log_runtime_error(self):
        self.error_count += 1
        log.warn('Failed to process article (%d so far)', self.error_count)

    def parse_simple(self, f):
        self.consumer.add_metadata('article_format', 'json')
        articles = self.articles(f)
        article_count = 0
        for a in articles:
            try:
                result = convert(a)
                title, serialized = result
                self.consumer.add_article(title, serialized)
                article_count += 1
            except RuntimeError:
                self.log_runtime_error()

        self.consumer.add_metadata("article_count", article_count)

    def parse_mp(self, f):
        try:
            self.consumer.add_metadata('article_format', 'json')
            articles = self.articles(f)
            self.reset_pool(f)
            resulti = self.pool.imap_unordered(convert, articles)
            article_count = 0
            while True:
                try:
                    result = resulti.next(self.timeout)
                    title, serialized = result
                    self.consumer.add_article(title, serialized)
                    article_count += 1
                except StopIteration:
                    break
                except TimeoutError:
                    self.timedout_count += 1
                    log.error('Worker pool timed out (%d time(s) so far)',
                                  self.timedout_count)
                    self.reset_pool(f)
                    resulti = self.pool.imap_unordered(convert, articles)
                except AssertionError:
                    self.log_runtime_error()
                except RuntimeError:
                    self.log_runtime_error()
                except KeyboardInterrupt:
                    log.error('Keyboard interrupt: '
                                  'terminating worker pool')
                    self.pool.terminate()
                    raise

            self.consumer.add_metadata("article_count", article_count)
        finally:
            self.pool.close()
            self.pool.join()
