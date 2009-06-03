import random

from aardtools.sortexternal import SortExternal

def test_with_ints():
    s = SortExternal()
    for i in range(100000):
        line = "%08i" % random.randint(0, 99999999)
        s.put(line)
    s.sort()
    prev = 0
    for line in s:
        val = int(line)
        assert val >= prev
    s.cleanup()
