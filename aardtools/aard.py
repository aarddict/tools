from aarddict import dictionary

class AardParser():
    
    def __init__(self, consumer):
        self.consumer = consumer
        
    def parse(self, f):
        d = dictionary.Dictionary(f, raw_articles=True)
        for key, val in d.metadata.iteritems():
            print key, val    
            self.consumer.add_metadata(key, val)
        for article_func in d.articles:                        
            self.consumer.add_article(article_func.title, article_func())
