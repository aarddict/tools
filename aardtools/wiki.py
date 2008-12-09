import functools 
import re
import logging

from lxml import etree
import simplejson

from mwlib import uparser, xhtmlwriter
from mwlib.log import Log
Log.logfile = None

import mwaardwriter

tojson = functools.partial(simplejson.dumps, ensure_ascii=False)

NS = '{http://www.mediawiki.org/xml/export-0.3/}'

from multiprocessing import Pool, TimeoutError
from mwlib.cdbwiki import WikiDB

def convert(data):
    title, text, templatesdir = data
    templatedb = WikiDB(templatesdir) if templatesdir else None
    mwobject = uparser.parseString(title=title, 
                                   raw=text, 
                                   wikidb=templatedb)
    xhtmlwriter.preprocess(mwobject)
    text, tags = mwaardwriter.convert(mwobject)
    return title, tojson((text.rstrip(), tags))


class WikiParser():
    
    def __init__(self, options, consumer):
        self.templatedir = options.templates
        self.consumer = consumer
        self.redirect_re = re.compile(r"\[\[(.*?)\]\]")
        self.article_count = 0
        self.processes = options.processes if options.processes else None 
        self.pool = Pool(processes=self.processes)
        self.timeout = options.timeout         
        self.timedout_count = 0
        
    def articles(self, f):
        for event, element in etree.iterparse(f):
            if element.tag == NS+'sitename':                
                self.consumer.add_metadata('title', element.text)
                element.clear()
                
            elif element.tag == NS+'base':
                m = re.compile(r"http://(.*?)\.wik").match(element.text)
                if m:
                    self.consumer.add_metadata("index_language", m.group(1))
                    self.consumer.add_metadata("article_language", m.group(1))
                                    
            elif element.tag == NS+'page':
                
                for child in element.iter(NS+'text'):
                    text = child.text
                
                if not text:
                    continue
                
                for child in element.iter(NS+'title'):
                    title = child.text
                    
                element.clear()

                if text.lstrip().lower().startswith("#redirect"): 
                    m = self.redirect_re.search(text)
                    if m:
                        redirect = m.group(1)
                        redirect = redirect.replace("_", " ")
                        meta = {u'redirect': redirect}
                        self.consumer.add_article(title, tojson(('', [], meta)))
                    continue
                logging.debug('Yielding "%s" for processing', title.encode('utf8'))                
                yield title, text, self.templatedir
                        
        
    def parse(self, f):
        try:
            self.consumer.add_metadata('article_format', 'json')
            articles = self.articles(f)
            resulti = self.pool.imap_unordered(convert, articles)
            while True:                                                                                         
                try:                                                                                            
                    result = resulti.next(self.timeout)                                                                 
                    title, serialized = result                                                                   
                    self.consumer.add_article(title, serialized)                                                
                    self.article_count += 1                                                                     
                except StopIteration:                                                                           
                    break            
                except TimeoutError:
                    self.timedout_count += 1
                    logging.error('Article timed out (%d so far)', 
                                  self.timedout_count)
                    logging.error('Terminating current worker pool')                                        
                    self.pool.terminate()
                    logging.error('Creating new worker pool')
                    self.pool = Pool(processes=self.processes)
                    resulti = self.pool.imap_unordered(convert, articles)
                    continue
                except KeyboardInterrupt:
                    logging.error('Keyboard interrupt: terminating worker pool')
                    self.pool.terminate()
                    self.pool.join()
                    raise
                    
            self.consumer.add_metadata("self.article_count", self.article_count)
        finally:
            self.pool.close()
            self.pool.join()
