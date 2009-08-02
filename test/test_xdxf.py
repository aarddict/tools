from aardtools import xdxf
from StringIO import StringIO
from collections import defaultdict
class Compiler:

    def __init__(self):
        self.articles = defaultdict(list)
        self.redirects = defaultdict(list)

    def add_article(self, title, serialized_article, redirect=False):
        if redirect:
            self.redirects[title].append(serialized_article)
        else:
            self.articles[title].append(serialized_article)

    def add_metadata(self, key, value):
        pass


def test_nu_tag():

    compiler = Compiler()
    parser = xdxf.XDXFParser(compiler)
    xdxf_xml = """<?xml version="1.0" encoding="UTF-8" ?>
<!DOCTYPE xdxf SYSTEM "http://xdxf.sourceforge.net/xdxf_lousy.dtd">
<xdxf lang_from="ENG" lang_to="ENG" format="visual">
<ar><k>abc<nu>|</nu>def</k>
</ar>
</xdxf>
"""
    parser.parse(StringIO(xdxf_xml))
    assert 'abcdef' in compiler.articles

def test_opt_tag():
    compiler = Compiler()
    parser = xdxf.XDXFParser(compiler)
    xdxf_xml = """<?xml version="1.0" encoding="UTF-8" ?>
<!DOCTYPE xdxf SYSTEM "http://xdxf.sourceforge.net/xdxf_lousy.dtd">
<xdxf lang_from="ENG" lang_to="ENG" format="visual">
<ar><k><opt>1</opt>a<opt>2</opt>b<opt>3</opt></k>
</ar>
</xdxf>
"""
    parser.parse(StringIO(xdxf_xml))
    assert 'ab' in compiler.articles
    for s in ('1ab', 'a2b', 'ab3', '1a2b', 'a2b3', '1ab3', '1a2b3'):
        assert s not in compiler.articles
        assert s in compiler.redirects

def test_multiple_k_tags():

    compiler = Compiler()
    parser = xdxf.XDXFParser(compiler)
    xdxf_xml = """<?xml version="1.0" encoding="UTF-8" ?>
<!DOCTYPE xdxf SYSTEM "http://xdxf.sourceforge.net/xdxf_lousy.dtd">
<xdxf lang_from="ENG" lang_to="ENG" format="visual">
<ar><k>a</k>, <k>b</k>, <k>c</k>
</ar>
</xdxf>
"""
    parser.parse(StringIO(xdxf_xml))
    assert 'a' in compiler.articles
    assert 'b' in compiler.redirects
    assert 'c' in compiler.redirects

def test_opt_and_nu_together():

    compiler = Compiler()
    parser = xdxf.XDXFParser(compiler)
    xdxf_xml = """<?xml version="1.0" encoding="UTF-8" ?>
<!DOCTYPE xdxf SYSTEM "http://xdxf.sourceforge.net/xdxf_lousy.dtd">
<xdxf lang_from="ENG" lang_to="ENG" format="visual">
<ar><k>abc<nu>|</nu>def<opt>g</opt></k>
</ar>
</xdxf>
"""
    parser.parse(StringIO(xdxf_xml))
    assert 'abcdef' in compiler.articles
    assert 'abcdefg' in compiler.redirects
