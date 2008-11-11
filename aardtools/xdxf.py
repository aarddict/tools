import logging
logging.basicConfig()
import functools 

from lxml import etree
import simplejson

tojson = functools.partial(simplejson.dumps, ensure_ascii=False)

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
                try:
                    title = element.find('k').text
                    self.consumer.add_article(title, tojson([txt, tags]))
                except:
                    logging.exception('Skipping bad article')
                finally:
                    element.clear()                        
