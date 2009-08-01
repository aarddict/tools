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

import sys

from aarddict import dictionary

def total(inputfile, options):
    d = dictionary.Dictionary(inputfile, raw_articles=True)
    d.close()
    return d.index_count

def collect_articles(input_file, options, compiler):
    p = AardParser(compiler)
    p.parse(input_file)

def make_input(input_file_name):
    if input_file_name == '-':
        return sys.stdin
    return open(input_file_name)

class AardParser():

    def __init__(self, consumer):
        self.consumer = consumer

    def parse(self, f):
        d = dictionary.Dictionary(f, raw_articles=True)
        for key, val in d.metadata.iteritems():
            print key, val
            self.consumer.add_metadata(key, val)
        for article_func in d.articles:
            decompressed_article = article_func()
            article = dictionary.to_article(decompressed_article)
            self.consumer.add_article(article_func.title, decompressed_article,
                                      redirect=article.redirect)
