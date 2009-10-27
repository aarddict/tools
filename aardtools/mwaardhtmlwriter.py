import xml.etree.ElementTree as ET

from mwlib import xhtmlwriter

EXCLUDE_CLASSES = set(('navbox', 'collapsible', 'autocollapse', 'plainlinksneverexpand', 'navbar'))

html_class_map = {'mwx.article': 'a',
                  'mwx.blockquote': 'b',
                  'mwx.categorylinks': 'c',
                  'mwx.chapter': 'd',
                  'mwx.gallery': 'e',
                  'mwx.hiero': 'f',
                  'mwx.hiero.alternate': 'g',
                  'mwx.image.float': 'h',
                  'mwx.image.inline': 'i',
                  'mwx.image.thumb': 'j',
                  'mwx.indented': 'k',
                  'mwx.languagelinks': 'l',
                  'mwx.link.article': 'm',
                  'mwx.link.category': 'n',
                  'mwx.link.external': 'o',
                  'mwx.link.image': 'p',
                  'mwx.link.interwiki': 'q',
                  'mwx.link.special': 'r',
                  'mwx.math': 's',
                  'mwx.reference': 't',
                  'mwx.references': 'u',
                  'mwx.section': 'v',
                  'mwx.source': 'w',
                  'mwx.style.center': 'x',
                  'mwx.style.overline': 'y',
                  'mwx.style.strike': 'z',
                  'mwx.style.underline': '1',
                  'mwx.timeline': '2',
                  'mwx.timeline.alternate': '3'
}

class XHTMLWriter(xhtmlwriter.MWXHTMLWriter):    

    paratag = 'p'

    def writeLanguageLinks(self):
        pass

    def xwriteImageLink(self, obj):
        return xhtmlwriter.SkipChildren()

    def xwriteImageMap(self, obj):
        return xhtmlwriter.SkipChildren()

    def xwriteGallery(self, obj):
        return xhtmlwriter.SkipChildren()

    def xwriteLink(self, obj):
        a = ET.Element("a", href=obj.target)
        a.set("class", "mwx.link.article")
        if not obj.children:
            a.text = obj.target
        return a

    xwriteArticleLink = xwriteLink
    xwriteInterwikiLink = xwriteLink
    xwriteNamespaceLink = xwriteLink

    def xwriteCategoryLink(self, obj):
        return xhtmlwriter.SkipChildren()        

    def xwriteTable(self, obj):
        tableclasses = obj.attributes.get('class', '').split()
        if any((tableclass in EXCLUDE_CLASSES for tableclass in tableclasses)):
            return xhtmlwriter.SkipChildren()
        return xhtmlwriter.MWXHTMLWriter.xwriteTable(self, obj)

    def xwriteGenericElement(self, obj):
        classes = obj.attributes.get('class', '').split()
        if any((cl in EXCLUDE_CLASSES for cl in classes)):
            return xhtmlwriter.SkipChildren()        
        return xhtmlwriter.MWXHTMLWriter.xwriteGenericElement(self, obj)        

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
        self.references.append(obj)
        group = obj.attributes.get(u'group', '')

        a = ET.Element("a")
        a.set("class", "mwx.reference")
        a.text = u'[%s]' % unicode( len(self.references))
        noteid = self.mknoteid(group, len(self.references))
        refid = u'_r'+noteid
        a.set('id', refid)
        a.set('href', '#')
        a.set('onClick', 
              'return s(\'%s\')' % noteid)        
        return xhtmlwriter.SkipChildren(a)

        
    def xwriteReferenceList(self, t):
        if not self.references:
            return
        ol = ET.Element("ol")
        ol.set("class", "mwx.references")
        for i, ref in enumerate(self.references):            
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
        self.references = []            
        return ol

    def mknoteid(self, group, num):
        return u'_n'+u'_'.join((group, unicode(num)))
        


def convert(obj):
    w = XHTMLWriter()
    e = w.write(obj)
    if w.languagelinks:
        languagelinks = [(obj.namespace, obj.target) for obj in w.languagelinks]
    else:
        languagelinks = []
    w.languagelinks = []
    text = ET.tostring(e, encoding='utf-8')

    text = text.replace(' class="mwx.paragraph"', '')

    for k, v in html_class_map.iteritems():
        text = text.replace(k, v)

    return text, [], languagelinks
