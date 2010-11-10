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

#original expression from
#http://stackoverflow.com/questions/694344/regular-expression-that-matches-between-quotes-containing-escaped-quotes
#"(?:[^\\"]+|\\.)*"
#some examples don't have closing quote which 
#make the subn with this expression hang
#quoted_text = re.compile(r'"(?:[^\\"]+|\\.)*["|\n]')

#make it a capturing group so that we can get rid of quotes
quoted_text = re.compile(r'"([^\\"]+|\\.)*["|\n]')

def total(inputfile, options):
    count = 1
    for line in iterlines(inputfile):
        count += 1
    return count

def collect_articles(input_file, options, compiler):
    p = WordNet(compiler)
    p.parse(input_file)

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


class WordNet():

    """
    The pointer_symbol s for nouns are:

    !    Antonym 
    @    Hypernym 
    @i    Instance Hypernym 
         Hyponym 
     i    Instance Hyponym 
    #m    Member holonym 
    #s    Substance holonym 
    #p    Part holonym 
    %m    Member meronym 
    %s    Substance meronym 
    %p    Part meronym 
    =    Attribute 
    +    Derivationally related form         
    ;c    Domain of synset - TOPIC 
    -c    Member of this domain - TOPIC 
    ;r    Domain of synset - REGION 
    -r    Member of this domain - REGION 
    ;u    Domain of synset - USAGE 
    -u    Member of this domain - USAGE 


    The pointer_symbol s for verbs are:

    !    Antonym 
    @    Hypernym 
         Hyponym 
    *    Entailment 
    >    Cause 
    ^    Also see 
    $    Verb Group 
    +    Derivationally related form         
    ;c    Domain of synset - TOPIC 
    ;r    Domain of synset - REGION 
    ;u    Domain of synset - USAGE 

    The pointer_symbol s for adjectives are:

    !    Antonym 
    &    Similar to 
    <    Participle of verb 
    \    Pertainym (pertains to noun) 
    =    Attribute 
    ^    Also see 
    ;c    Domain of synset - TOPIC 
    ;r    Domain of synset - REGION 
    ;u    Domain of synset - USAGE 

    The pointer_symbol s for adverbs are:

    !    Antonym 
    \    Derived from adjective 
    ;c    Domain of synset - TOPIC 
    ;r    Domain of synset - REGION 
    ;u    Domain of synset - USAGE 


    """

    def __init__(self, consumer):
        self.consumer = consumer 
        self.collector = {}

    def parse(self, wordnetdir):

        readme_file = os.path.join(wordnetdir, 'README')
        license_file = os.path.join(wordnetdir, 'LICENSE')

        self.consumer.add_metadata('title', 'WordNet')
        self.consumer.add_metadata('version', '3.0')
        self.consumer.add_metadata('index_language', 'en')
        self.consumer.add_metadata('article_language', 'en')

        with open(readme_file) as f:
            self.consumer.add_metadata('description', '<pre>%s</pre>' % f.read())

        with open(license_file) as f:
            self.consumer.add_metadata('license', f.read())

        ss_types = {'n': 'noun',
                    'v': 'verb',
                    'a': 'adjective',
                    's': 'adjective satellite',
                    'r': 'adverb'}

        for line in iterlines(wordnetdir):
            meta, gloss = line.split('|')
            meta_parts = meta.split()
            synset_offset = meta_parts[0]
            lex_filenum = meta_parts[1]
            ss_type = meta_parts[2]
            w_cnt = meta_parts[3]
            word_count = int(w_cnt, 16)
            word = meta_parts[4]

            orig_title = title = word.replace('_', ' ')
            # print gloss
            gloss_with_examples, _ = quoted_text.subn(lambda x: '<span class="ex">%s<span>' % 
                                                   x.group(1), gloss)
            # print gloss_with_examples
            text = ('<span><b>%s</b><br><span class="pos">%s</span> %s</span>' %
                    (title,
                     ss_types[ss_type],
                     gloss_with_examples))

            self.consumer.add_article(title,
                                      json.dumps((text, [], {})),
                                      redirect=False)

            if word_count > 1:
                for i in range(1, word_count):
                    word = meta_parts[4+2*i]
                    title = word.replace('_', ' ')
                    self.consumer.add_article(title,
                                              json.dumps(('', [], {'r': orig_title})),
                                              redirect=True, count=False)
                    
