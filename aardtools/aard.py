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

from aarddict import dictionary


import collections
from aardtools.compiler import ArticleSource, Article


class AardArticleSource(ArticleSource, collections.Sized):

    @classmethod
    def register_argparser(cls, subparsers, parents):
        parser = subparsers.add_parser('aard', parents=parents)
        parser.set_defaults(article_source_class=cls)

    def __init__(self, args):
        super(AardArticleSource, self).__init__(self)
        self.input_files = args.input_files
        self._metadata = {}

    @property
    def metadata(self):
        return self._metadata

    def __len__(self):
        count = 0
        for name in self.input_files:
            d = dictionary.Volume(name)
            count += len(d)
            d.close()
        return count

    def __iter__(self):
        for name in self.input_files:
            d = dictionary.Volume(name)
            self._metadata.update(d.metadata)
            for i, article in enumerate(d.articles):
                title= d.words[i]
                yield Article(title, article)
            d.close()
