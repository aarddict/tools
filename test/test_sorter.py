import random
import string
from aardtools.compiler import Sorter

def setup():
    global sorter, data
    sorter = Sorter()
    data = [random_word() for i in range(100)]
    for x in data:
        sorter.append(x)

def random_word():
    length = random.randint(1, 20)
    letters = list()
    for i in range(length):
        letters.append(random.choice(string.letters))
    return ''.join(letters)

def teardown():
    sorter.close()

def test_without_key():
    assert list(sorter.sorted()) == sorted(data)

def test_with_key():
    key = lambda x: ''.join(reversed(x))
    assert list(sorter.sorted(key=key)) == sorted(data, key=key)
