import random
import string
from aardtools.compiler import TempArticleStore

def setup():
    global store, data
    store = TempArticleStore()
    random_words = [random_word() for i in range(100)]
    data = [(word, 'article %s' % word) for word in random_words]
    for title, article in data:
        store.append(title, article)

def random_word():
    length = random.randint(1, 20)
    letters = list()
    for i in range(length):
        letters.append(random.choice(string.letters))
    return ''.join(letters)

def teardown():
    store.close()

def test_without_key():
    assert list(store.sorted()) == sorted(data, key=lambda x: x[0])

def test_with_key():
    actual = list(store.sorted(key=lambda x: ''.join(reversed(x))))
    expected = sorted(data, key=lambda x: ''.join(reversed(x[0])))
    assert actual == expected, 'actual:\n%r\nexpected:\n%r\n' % (actual, expected)
