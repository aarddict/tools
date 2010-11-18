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

import os
import json
import re
import mmap

from collections import defaultdict

#original expression from
#http://stackoverflow.com/questions/694344/regular-expression-that-matches-between-quotes-containing-escaped-quotes
#"(?:[^\\"]+|\\.)*"
#some examples don't have closing quote which
#make the subn with this expression hang
#quoted_text = re.compile(r'"(?:[^"]+|\.)*["|\n]')

#make it a capturing group so that we can get rid of quotes
quoted_text = re.compile(r'"([^"]+|\.)*["|\n]')

ref = re.compile(r"`(\w+)'")

wordnet = None

def total(inputfile, options):
    global wordnet
    wordnet = WordNet(inputfile)
    wordnet.prepare()
    count = 0
    for title in wordnet.collector:
        has_article = False
        for piece in wordnet.collector[title]:
            if isinstance(piece, tuple):
                count += 1
            else:
                has_article = True
        if has_article:
            count += 1
    return count


def collect_articles(input_file, options, compiler):
    wordnet.process(compiler)

def make_input(input_file_name):
    return input_file_name #this should be wordnet dir, leave it alone

def iterlines(wordnetdir):
    dict_dir = os.path.join(wordnetdir, 'dict')
    for name in os.listdir(dict_dir):
        if name.startswith('data.'):
            with open(os.path.join(dict_dir, name)) as f:
                for line in f:
                    if not line.startswith('  '):
                        yield line

class SynSet(object):

    def __init__(self, line):
        self.line = line
        meta, self.gloss = line.split('|')
        self.meta_parts = meta.split()

    @property
    def offset(self):
        return int(self.meta_parts[0])

    @property
    def lex_filenum(self):
        return self.meta_parts[1]

    @property
    def ss_type(self):
        return self.meta_parts[2]

    @property
    def w_cnt(self):
        return int(self.meta_parts[3], 16)

    @property
    def words(self):
        return [self.meta_parts[4+2*i].replace('_', ' ')
                for i in range(self.w_cnt)]

    @property
    def pointers(self):
        p_cnt_index = 4+2*self.w_cnt
        p_cnt = self.meta_parts[p_cnt_index]
        pointer_count = int(p_cnt)
        start = p_cnt_index + 1
        return [Pointer(*self.meta_parts[start+i*4:start+(i+1)*4])
                for i in range(pointer_count)]

    def __repr__(self):
        return 'SynSet(%r)' % self.line


class PointerSymbols(object):

    n = {'!':    'Antonyms',
         '@':    'Hypernyms',
         '@i':   'Instance hypernyms',
         '~':    'Hyponyms',
         '~i':   'Instance hyponyms',
         '#m':   'Member holonyms',
         '#s':   'Substance holonyms',
         '#p':   'Part holonyms',
         '%m':   'Member meronyms',
         '%s':   'Substance meronyms',
         '%p':   'Part meronyms',
         '=':    'Attributes',
         '+':    'Derivationally related forms',
         ';c':   'Domain of synset - TOPIC',
         '-c':   'Member of this domain - TOPIC',
         ';r':   'Domain of synset - REGION',
         '-r':   'Member of this domain - REGION',
         ';u':   'Domain of synset - USAGE',
         '-u':   'Member of this domain - USAGE'}

    v = {'!':   'Antonyms',
         '@':   'Hypernyms',
         '~':   'Hyponyms',
         '*':   'Entailments',
         '>':   'Cause',
         '^':   'Also see',
         '$':   'Verb group',
         '+':   'Derivationally related forms',
         ';c':  'Domain of synset - TOPIC',
         ';r':  'Domain of synset - REGION',
         ';u':  'Domain of synset - USAGE'}

    a = s = {'!':   'Antonyms',
             '+':   'Derivationally related forms',
             '&':   'Similar to',
             '<':   'Participle of verb',
             '\\':  'Pertainyms',
             '=':   'Attributes',
             '^':   'Also see',
             ';c':  'Domain of synset - TOPIC',
             ';r':  'Domain of synset - REGION',
             ';u':  'Domain of synset - USAGE'}

    r = {'!':   'Antonyms',
         '\\':  'Derived from adjective',
         '+':   'Derivationally related forms',
         ';c':  'Domain of synset - TOPIC',
         ';r':  'Domain of synset - REGION',
         ';u':  'Domain of synset - USAGE'}


class Pointer(object):

    def __init__(self, symbol, offset, pos, source_target):
        self.symbol = symbol
        self.offset = int(offset)
        self.pos = pos
        self.source_target = source_target
        self.source = int(source_target[:2], 16)
        self.target = int(source_target[2:], 16)

    def __repr__(self):
        return ('Pointer(%r, %r, %r, %r)' %
                (self.symbol, self.offset,
                 self.pos, self.source_target))


class WordNet():

    def __init__(self, wordnetdir):
        self.wordnetdir = wordnetdir
        self.collector = defaultdict(list)

    def prepare(self):

        ss_types = {'n': 'n.',
                    'v': 'v.',
                    'a': 'adj.',
                    's': 'adj. satellite',
                    'r': 'adv.'}

        file2pos = {'data.adj': ['a', 's'],
                    'data.adv': ['r'],
                    'data.noun': ['n'],
                    'data.verb': ['v']}

        dict_dir = os.path.join(self.wordnetdir, 'dict')

        mmap_files = {}
        for name in os.listdir(dict_dir):
            if name.startswith('data.'):
                if name in file2pos:
                    f = open(os.path.join(dict_dir, name), 'r+')
                    m = mmap.mmap(f.fileno(), 0)
                    for key in file2pos[name]:
                        mmap_files[key] = m

        def a(word):
            return '<a href="%s">%s</a>' % (word, word)

        for line in iterlines(self.wordnetdir):
            synset = SynSet(line)
            gloss_with_examples, _ = quoted_text.subn(lambda x: '<cite class="ex">%s</cite>' %
                                                   x.group(1), synset.gloss)
            gloss_with_examples, _ = ref.subn(lambda x: a(x.group(1)), gloss_with_examples)

            words = synset.words
            for i, word in enumerate(words):
                synonyms = [w for w in words if w != word]
                synonyms_str = ('<br/><small class="co">Synonyms:</small> %s' %
                                ', '.join([a(w) for w in synonyms]) if synonyms else '')
                pointers = defaultdict(list)
                for pointer in synset.pointers:
                    if (pointer.source and pointer.target and
                        pointer.source - 1 != i):
                        continue
                    symbol = pointer.symbol
                    if symbol and symbol[:1] in (';', '-'):
                        continue
                    try:
                        symbol_desc = getattr(PointerSymbols, synset.ss_type)[symbol]
                    except KeyError:
                        print 'WARNING: unknown pointer symbol %s for %s ' % (symbol, synset.ss_type)
                        symbol_desc = symbol

                    mmap_file = mmap_files[pointer.pos]
                    mmap_file.seek(pointer.offset)
                    referenced_synset = SynSet(mmap_file.readline())
                    if pointer.source == 0 and pointer.target == 0:
                        pointers[symbol_desc] = [w for w in referenced_synset.words
                                                 if w not in words]
                    else:
                        referenced_word = referenced_synset.words[pointer.target - 1]
                        if referenced_word not in pointers[symbol_desc]:
                            pointers[symbol_desc].append(referenced_word)

                pointers_str = ''
                for symbol_desc, referenced_words in pointers.iteritems():
                    if referenced_words:
                        pointers_str += '<br/><small class="co">%s:</small> ' % symbol_desc
                        pointers_str += ', '.join([a(w) for w in referenced_words])
                self.collector[word].append('<i class="pos">%s</i> %s%s%s' %
                                            (ss_types[synset.ss_type],
                                             gloss_with_examples,
                                             synonyms_str,
                                             pointers_str))



    def process(self, consumer):

        readme_file = os.path.join(self.wordnetdir, 'README')
        license_file = os.path.join(self.wordnetdir, 'LICENSE')

        consumer.add_metadata('title', 'WordNet')
        consumer.add_metadata('index_language', 'en')
        consumer.add_metadata('article_language', 'en')
        consumer.add_metadata('source', 'http://wordnet.princeton.edu')

        with open(readme_file) as f:
            readme = f.read()
            lines = readme.splitlines()
            lines = lines[5:]
            first_p_index = lines.index('')
            first_p = ' '.join(lines[:first_p_index])
            lines = lines[first_p_index+1:]
            second_p_index = lines.index('')
            second_p = ' '.join(lines[:second_p_index])
            aard_p = ('WordNet for Aard Dictionary is a collection of articles '
                      'consisting of all meanings of a given word and links '
                      'to lexically and sematically related words.')
            consumer.add_metadata('description', 
                                  '\n\n'.join((first_p, second_p, aard_p)))

        with open(license_file) as f:
            license_text = f.read()
            aard_p = """(This is original WordNet license text. 
Note that the software covered by this license 
is WordNet software, not Aard Dictionary.)
"""
            consumer.add_metadata('license', '\n'.join((aard_p, license_text)))
            version = license_text.splitlines()[0].split()[-1]
            consumer.add_metadata('version', version)

        article_template = '<h1>%s</h1><span>%s</span>'

        for title in self.collector:
            pieces = self.collector[title]
            article_pieces = []
            redirects = []
            for piece in pieces:
                if isinstance(piece, tuple):
                    redirects.append(piece)
                else:
                    article_pieces.append(piece)

            article_pieces_count = len(article_pieces)

            text = None
            if article_pieces_count > 1:
                ol = ['<ol>'] + ['<li>%s</li>' % ap for ap in article_pieces] + ['</ol>']
                text = (article_template % (title, ''.join(ol)))
            elif article_pieces_count == 1:
                text = (article_template %
                        (title, article_pieces[0]))

            if text:
                consumer.add_article(title,
                                     json.dumps((text, [])),
                                     redirect=False)

            #add redirects after articles so that
            #redirects to titles that have both articles and
            #redirects land on articles
            for redirect in redirects:
                consumer.add_article(title,
                                     json.dumps(redirect),
                                     redirect=True)
