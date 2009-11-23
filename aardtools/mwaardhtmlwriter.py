import logging
import xml.etree.ElementTree as ET

from collections import defaultdict

from mwlib.xhtmlwriter import MWXHTMLWriter, SkipChildren

import tex

EXCLUDE_CLASSES = set(('navbox', 'collapsible', 'autocollapse', 'plainlinksneverexpand', 'navbar'))


log = logging.getLogger(__name__)

class XHTMLWriter(MWXHTMLWriter):    

    paratag = 'p'

    def __init__(self, *args, **kwargs):
        MWXHTMLWriter.__init__(self, *args, **kwargs)
        #keep reference list for each group serparate
        self.references = defaultdict(list)

    def xwriteArticle(self, a):
        e = ET.Element("div")
        h = ET.SubElement(e, "h1")
        h.text = a.caption
        self.writeChildren(a, e)
        return SkipChildren(e)

    def xwriteChapter(self, obj):
        e = ET.Element("div")
        h = ET.SubElement(e, "h1")
        self.write(obj.caption)
        return e

    def xwriteSection(self, obj):
        e = ET.Element("div")
        level = 2 + obj.getLevel() # starting with h2
        h = ET.SubElement(e, "h%d" % level)
        self.write(obj.children[0], h)
        obj.children = obj.children[1:]
        return e

    def xwriteTimeline(self, obj): 
        s = ET.Element("object")
        s.set("type", "application/mediawiki-timeline")
        s.set("src", "data:text/plain;charset=utf-8,%s" % obj.caption)
        em = ET.SubElement(s, "em")
        em.text = u"Timeline"
        return s

    def xwriteHiero(self, obj): # FIXME parser support
        s = ET.Element("object")
        s.set("type", "application/mediawiki-hiero")
        s.set("src", "data:text/plain;charset=utf-8,%s" % obj.caption)
        em = ET.SubElement(s, "em")
        em.text = u"Hiero"
        return s

    def xwriteMath(self, obj):        
        try:
            imgurl = 'data:image/png;base64,' + tex.toimg(obj.caption)
        except:
            log.exception('Failed to rendered math "%r"', obj.caption)
            s = ET.Element("span")
            s.text = obj.caption
            s.set("class", "tex")
        else:
            s = ET.Element("img")
            s.set("src", imgurl)
            s.set("class", "tex")
        return s

    def xwriteURL(self, obj):
        a = ET.Element("a", href=obj.caption)
        a.set("class", "mwx.link.external")
        if not obj.children:
            a.text = obj.caption
        return a

    def xwriteNamedURL(self, obj):
        a = ET.Element("a", href=obj.caption)
        if not obj.children:
            name = "[%s]" % self.namedLinkCount
            self.namedLinkCount += 1
            a.text = name
        return a

    def xwriteSpecialLink(self, obj): # whats that?
        a = ET.Element("a", href=obj.url or "#")
        if not obj.children:
            a.text = obj.target
        return a

    def writeLanguageLinks(self):
        pass

    def xwriteImageLink(self, obj):
        return SkipChildren()

    def xwriteImageMap(self, obj):
        return SkipChildren()

    def xwriteGallery(self, obj):
        return SkipChildren()

    def xwriteLink(self, obj):
        a = ET.Element("a", href=obj.target)
        if not obj.children:
            a.text = obj.target
        return a

    xwriteArticleLink = xwriteLink
    xwriteInterwikiLink = xwriteLink
    xwriteNamespaceLink = xwriteLink

    def xwriteCategoryLink(self, obj):
        return SkipChildren()        

    def xwriteTable(self, obj):
        tableclasses = obj.attributes.get('class', '').split()
        if any((tableclass in EXCLUDE_CLASSES for tableclass in tableclasses)):
            return SkipChildren()
        return MWXHTMLWriter.xwriteTable(self, obj)

    def xwriteGenericElement(self, obj):
        classes = obj.attributes.get('class', '').split()
        if any((cl in EXCLUDE_CLASSES for cl in classes)):
            return SkipChildren()        
        return MWXHTMLWriter.xwriteGenericElement(self, obj)        

    xwriteEmphasized = xwriteGenericElement
    xwriteStrong = xwriteGenericElement
    xwriteSmall = xwriteGenericElement
    xwriteBig = xwriteGenericElement
    xwriteCite = xwriteGenericElement
    xwriteSub = xwriteGenericElement
    xwriteSup = xwriteGenericElement
    xwriteCode = xwriteGenericElement
    xwriteBreakingReturn = xwriteGenericElement
    xwriteHorizontalRule = xwriteGenericElement
    xwriteTeletyped = xwriteGenericElement
    xwriteDiv = xwriteGenericElement
    xwriteSpan = xwriteGenericElement
    xwriteVar= xwriteGenericElement
    xwriteRuby = xwriteGenericElement
    xwriteRubyBase = xwriteGenericElement
    xwriteRubyParentheses = xwriteGenericElement
    xwriteRubyText = xwriteGenericElement
    xwriteDeleted = xwriteGenericElement
    xwriteInserted = xwriteGenericElement
    xwriteTableCaption = xwriteGenericElement
    xwriteDefinitionList = xwriteGenericElement
    xwriteDefinitionTerm = xwriteGenericElement
    xwriteDefinitionDescription = xwriteGenericElement
    xwriteFont = xwriteGenericElement

    def xwriteReference(self, obj):
        assert obj is not None
        group = obj.attributes.get(u'group', '')
        group_references = self.references[group]
        group_references.append(obj)
        a = ET.Element("a")
        a.text = u'%s %s' % (group, unicode(len(group_references)))
        a.text = u'[%s]' % a.text.strip()
        noteid = self.mknoteid(group, len(group_references))
        refid = u'_r'+noteid
        a.set('id', refid)
        a.set('href', '#')
        a.set('onClick', 
              'return s(\'%s\')' % noteid)        
        return SkipChildren(a)
        
    def xwriteReferenceList(self, t):
        if not self.references:
            return
        references = self.references.pop(t.attributes['group'])        
        if not references:
            return        
        ol = ET.Element("ol")
        for i, ref in enumerate(references):
            group = ref.attributes.get(u'group', '')
            noteid = self.mknoteid(group, i+1)
            li = ET.SubElement(ol, "li", id=noteid)
            b = ET.SubElement(li, "b")
            b.tail = ' '
            ref_id = u'_r'+noteid
            backref = ET.SubElement(b, 'a', href=u'#'+ref_id)
            backref.set('onClick', 
                        'return s(\'%s\')' % (ref_id))
            backref.text = u'^'
            self.writeChildren(ref, parent=li)
        return ol

    def mknoteid(self, group, num):
        return u'_n'+u'_'.join((group, unicode(num)))

    def xwriteParagraph(self, obj):
        """
        currently the parser encapsulates almost anything into paragraphs, 
        but XHTML1.0 allows no block elements in paragraphs.
        therefore we use the html-div-element. 

        this is a hack to let created documents pass the validation test.
        """
        e = ET.Element(self.paratag) # "div" or "p"
        return e

    def xwriteOverline(self, s):
        e = ET.Element("span")
        e.set("class", "o")
        return e    

    def xwriteUnderline(self, s):
        e = ET.Element("span")
        e.set("class", "u")
        return e

    def xwriteSource(self, s):       
        e = ET.Element("code")
        return e
    
    def xwriteCenter(self, s):
        e = ET.Element("span")
        e.set("class", "center")
        return e

    def xwriteStrike(self, s):
        e = ET.Element("del")
        return e

    def xwriteBlockquote(self, s):
        return ET.Element("blockquote")

    def xwriteIndented(self, s):
        e = ET.Element("blockquote")
        e.set("class", "indent")
        return e
    

def convert(obj):
    w = XHTMLWriter()
    e = w.write(obj)
    if w.languagelinks:
        languagelinks = [(obj.namespace, obj.target) for obj in w.languagelinks]
    else:
        languagelinks = []
    w.languagelinks = []
    text = ET.tostring(e, encoding='utf-8')
    return text, [], languagelinks
