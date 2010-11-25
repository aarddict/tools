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

def total(inputfile, options):
    d = dictionary.Volume(inputfile)
    d.close()
    return len(d)

def collect_articles(input_file, options, compiler):
    p = AardParser(compiler)
    p.parse(input_file)

def make_input(input_file_name):
    return input_file_name

class AardParser():

    def __init__(self, consumer):
        self.consumer = consumer

    def parse(self, f):
        d = dictionary.Volume(f)
        for key, val in d.metadata.iteritems():
            self.consumer.add_metadata(key, val)
        for i, article in enumerate(d.articles):
            title= d.words[i]
            self.consumer.add_article(title, article)
        d.close()
