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
