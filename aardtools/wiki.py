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

#from lxml import etree
from xml.etree import cElementTree as etree
import simplejson

from mwlib import uparser, xhtmlwriter
from mwlib.log import Log
Log.logfile = None

import mwaardwriter

tojson = functools.partial(simplejson.dumps, ensure_ascii=False)

NS = '{http://www.mediawiki.org/xml/export-0.3/}'
XMLNS = '{http://www.w3.org/XML/1998/namespace}'

import multiprocessing
from multiprocessing import Pool, TimeoutError
from mwlib.cdbwiki import WikiDB

import mem

def convert(data):
    title, text, templatesdir, lang = data
    templatedb = WikiDB(templatesdir) if templatesdir else None
    try:
        mwobject = uparser.parseString(title=title, 
                                       raw=text, 
                                       wikidb=templatedb,
                                       lang=lang)        
        xhtmlwriter.preprocess(mwobject)
        text, tags = mwaardwriter.convert(mwobject)
    except RuntimeError:
        multiprocessing.get_logger().exception('Failed to process article %s', title)
        raise
    return title, tojson((text.rstrip(), tags))

def mem_check(rss_threshold=0, rsz_threshold=0, vsz_threshold=0):
    """
    Check memory usage for active child processes and return list of processes
    that exceed specified memory usage threshold (in megabytes). Threshold considered not set
    if it's value is 0 (which is default for all thresholds)
    """
    active = multiprocessing.active_children()
    logging.info('Checking memory usage (%d child processes), thresholds: rss %.1fM rsz %.1fM vsz %.1fM',
                 len(active), rss_threshold, rsz_threshold, vsz_threshold)
    processes = []
    for process in active:
        pid = process.pid
        logging.info('Checking memory usage for process %d', pid)
        rss = rsz = vsz = 0

        if 0 < rss_threshold:
            rss = mem.rss(pid) / 1024.0
            if rss_threshold <= rss:
                logging.warn('Process %d exceeded rss memory limit of %.1fM',
                             pid, rss_threshold)                
                processes.append(process)

        if 0 < rsz_threshold:
            rsz = mem.rsz(pid) / 1024.0
            if rsz_threshold <= rsz:
                logging.warn('Process %d exceeded rsz memory limit of %.1fM',
                             pid, rsz_threshold)                                
                processes.append(process)

        if 0 < vsz_threshold:
            vsz = mem.vsz(pid) / 1024.0
            if vsz_threshold <= vsz:
                logging.warn('Process %d exceeded vsz memory limit of %.1fM',
                             pid, vsz_threshold)                                
                processes.append(process)
                
        logging.info('Pid %d: rss %.1fM rsz %.1fM vsz %.1fM', pid, rss, rsz, vsz)
    return processes

class WikiParser():
    
    def __init__(self, options, consumer):
        self.templatedir = options.templates
        self.mem_check_freq = options.mem_check_freq
        self.consumer = consumer
        self.redirect_re = re.compile(r'\[\[(.*?)\]\]', re.UNICODE)
        self.special_article_re = re.compile(r'^\w+:\S', re.UNICODE)
        self.article_count = 0
        self.skipped_count = 0
        self.processes = options.processes if options.processes else None 
        self.pool = None
        self.active_processes = multiprocessing.active_children()
        self.timeout = options.timeout         
        self.timedout_count = 0
        self.error_count = 0
        self.rss_threshold = options.rss_threshold
        self.rsz_threshold = options.rsz_threshold
        self.vsz_threshold = options.vsz_threshold
        self.start = options.start
        self.end = options.end
        self.read_count = 0
        self.lang = None
        if options.nomp:
            logging.info('Disabling multiprocessing')
            self.parse = self.parse_simple
        else:
            self.parse = self.parse_mp
        
    def _set_lang(self, lang):
        self.lang = lang
        self.consumer.add_metadata("index_language", lang)
        self.consumer.add_metadata("article_language", lang)
        logging.info('Language: %s', self.lang)        
        
    def articles(self, f):
        if self.start > 0:
            logging.info('Skipping to article %d', self.start)

        #context = etree.iterparse(f, events=("start", "end"), remove_blank_text=True, remove_comments=True, remove_pis=True)
        context = etree.iterparse(f, events=("start", "end"))
        context = iter(context)

        event, root = context.next()
        
        lang_attr = XMLNS+'lang'
        if lang_attr in root.attrib:
            self._set_lang(root.attrib[lang_attr])

        for event, element in context:
            if event == 'end':
                if element.tag == NS+'sitename':                
                    self.consumer.add_metadata('title', element.text)
                elif element.tag == NS+'siteinfo':
                    root.clear()
                elif not self.lang and element.tag == NS+'base':
                    m = re.compile(r"http://(.*?)\.wik").match(element.text)
                    if m:
                        self._set_lang(m.group(1))
                elif element.tag == NS+'page':

                    self.read_count += 1

                    if self.read_count <= self.start:
                        root.clear()
                        if self.read_count % 10000 == 0:
                            logging.info('Skipped %d', self.read_count)
                        continue

                    if self.end and self.read_count > self.end:
                        logging.info('Reached article %d, stopping.', self.end)
                        root.clear()
                        break

                    for child in element.getiterator(NS+'text'):
                        text = child.text

                    if not text:
                        root.clear()
                        continue

                    for child in element.getiterator(NS+'title'):
                        title = child.text

                    root.clear()

                    if self.special_article_re.match(title):
                        self.skipped_count += 1
                        logging.info('Special article %s, skipping (%d so far)',
                                     title.encode('utf8'), self.skipped_count)
                        continue

                    if text.lstrip().lower().startswith("#redirect"): 
                        m = self.redirect_re.search(text)
                        if m:
                            redirect = m.group(1)
                            redirect = redirect.replace("_", " ")
                            meta = {u'redirect': redirect}
                            self.consumer.add_article(title, tojson(('', [], meta)))
                        continue
                    logging.debug('Yielding "%s" for processing', title.encode('utf8'))                
                    yield title, text, self.templatedir, self.lang

    def reset_pool(self):
        if self.pool:
            logging.info('Terminating current worker pool')
            self.pool.terminate()
        logging.info('Creating new worker pool')
        self.pool = Pool(processes=self.processes)

    def log_runtime_error(self):
        self.error_count += 1
        logging.warn('Failed to process article (%d so far)', self.error_count)

    def parse_simple(self, f):
        self.consumer.add_metadata('article_format', 'json')
        articles = self.articles(f)
        for a in articles:
            try:
                result = convert(a)
                title, serialized = result
                self.consumer.add_article(title, serialized)
            except RuntimeError:
                self.log_runtime_error()
                
        self.consumer.add_metadata("self.article_count", self.article_count)
        
    def parse_mp(self, f):
        try:
            self.consumer.add_metadata('article_format', 'json')
            articles = self.articles(f)
            self.reset_pool()
            resulti = self.pool.imap_unordered(convert, articles)
            while True:
                try:
                    result = resulti.next(self.timeout)
                    title, serialized = result
                    self.consumer.add_article(title, serialized)
                    self.article_count += 1
                    if (self.mem_check_freq != 0) and ((self.article_count % self.mem_check_freq) == 0):                
                        processes = mem_check(rss_threshold=self.rss_threshold,
                                              rsz_threshold=self.rsz_threshold,
                                              vsz_threshold=self.vsz_threshold)
                        if processes:
                            logging.warn('%d process(es) exceeded memory limit, resetting worker pool',
                                         len (processes))
                            self.reset_pool()
                            resulti = self.pool.imap_unordered(convert, articles)
                except StopIteration:
                    break            
                except TimeoutError:
                    self.timedout_count += 1
                    logging.error('Worker pool timed out (%d time(s) so far)', 
                                  self.timedout_count)
                    self.reset_pool()
                    resulti = self.pool.imap_unordered(convert, articles)
                except RuntimeError:
                    self.log_runtime_error()
                except KeyboardInterrupt:
                    logging.error('Keyboard interrupt: terminating worker pool')
                    self.pool.terminate()
                    raise                
                    
            self.consumer.add_metadata("article_count", self.article_count)
        finally:
            self.pool.close()
            self.pool.join()
