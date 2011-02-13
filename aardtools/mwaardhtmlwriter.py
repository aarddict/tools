import logging
import xml.etree.ElementTree as ET

from collections import defaultdict

from mwlib.xhtmlwriter import MWXHTMLWriter, SkipChildren
from mwlib import xmltreecleaner
from mwlib.advtree import Reference
xmltreecleaner.childlessOK.append(Reference)

import tex

EXCLUDE_CLASSES = frozenset(('navbox', 'collapsible', 'autocollapse',
                             'plainlinksneverexpand', 'navbar', 'metadata',
                             'navigation-box', 'stub', 'template-documentation',
                             'portal', 'NavFrame', 'NavHead', 'NavContent', 'thumbinner',
                             'thumbcaption', 'magnify', 'vertical-navbox',
                             'tmbox', 'maptable', 'printonly',
                             'fmbox', 'ombox', 'cmbox', 'sisterproject', 
                             'interProject',
                             'wikilien_alternatif', #frwiki sister projects
                             'bandeau', #frwiki message at the top of article
                             'itwiki_template_avviso', #itwiki
                             'itwiki_template_toc',
                             'itwiki_template_disclaimer_v',
                             ))

EXCLUDED_IDS = frozenset(('interProject',))

log = logging.getLogger(__name__)

#latex can render most math, generates nice transparent PNG, but fails on some formulas
#blahtex can render some formulas that latex can't, also renders transparent PNG
#texvc is what Wikipedia uses, can render the most, but output PNG is not transparent and
#doesn't looks as good as latex or blahtex
mathcmds = ('latex', 'blahtex', 'texvc')

class XHTMLWriter(MWXHTMLWriter):

    paratag = 'p'

    def __init__(self, *args, **kwargs):
        MWXHTMLWriter.__init__(self, *args, **kwargs)
        #keep reference list for each group serparate
        self.references = defaultdict(list)
        #also keep named reference positions, separate for each group
        #map named reference to 2-tuple of position first seen and count
        self.namedrefs = defaultdict(dict)

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
        for cmd in mathcmds:
            try:
                imgurl = 'data:image/png;base64,' + tex.toimg(obj.caption, cmd)
            except tex.MathRenderingFailed, e:
                log.warn('Could not render math in %r with %r: %s',
                         obj.getParents()[0].caption, cmd, e)
            except:
                log.warn('Could not render math in %r with %r',
                         obj.getParents()[0].caption, cmd, exc_info=1)
            else:
                s = ET.Element("img")
                s.set("src", imgurl)
                s.set("class", "tex")
                return s
        log.error('Failed to render math %r in %r',
                  obj.caption, obj.getParents()[0].caption)
        s = ET.Element("span")
        s.text = obj.caption
        s.set("class", "tex")
        return s

    def xwriteURL(self, obj):
        a = ET.Element("a", href=obj.caption)
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

    def xwriteItemList(self, lst):
        for li in lst.children:
            if any(c.ns == 10 for c in li.children):
                return SkipChildren()
        if lst.numbered:
            tag = "ol"
        else:
            tag = "ul"
        return ET.Element(tag)

    xwriteArticleLink = xwriteLink
    xwriteInterwikiLink = xwriteLink
    xwriteNamespaceLink = xwriteLink

    def xwriteCategoryLink(self, obj):
        return SkipChildren()

    def xwriteTable(self, obj):
        tableclasses = obj.attributes.get('class', '').split()
        if any((tableclass in EXCLUDE_CLASSES for tableclass in tableclasses)):
            return SkipChildren()
        id_attr = obj.attributes.get('id', '')
        if id_attr in EXCLUDED_IDS:
            return SkipChildren()
        return MWXHTMLWriter.xwriteTable(self, obj)

    def xwriteGenericElement(self, obj):
        classes = obj.attributes.get('class', '').split()
        if any((cl in EXCLUDE_CLASSES for cl in classes)):
            return SkipChildren()
        id_attr = obj.attributes.get('id', '')
        if id_attr in EXCLUDED_IDS:
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

        a = ET.Element("a")
        ref_name = obj.attributes.get('name')
        if ref_name:
            ref_name = ref_name.replace(' ', '_')
            group_namedrefs = self.namedrefs[group]
            named_ref_first, named_ref_count = group_namedrefs.get(ref_name, (None, 0))
            if named_ref_first is None:
                log.debug('adding named ref %r', ref_name)
                group_references.append(obj)
                named_ref_first = len(group_references)
            elif obj.children:
                group_references[named_ref_first-1] = obj
            note_seq_num = named_ref_first
            noteid = self.mknoteid(group, named_ref_first)
            refid = u'_r'+noteid+u'_'+str(named_ref_count)
            named_ref_count += 1
            group_namedrefs[ref_name] = (named_ref_first, named_ref_count)
        else:
            group_references.append(obj)
            note_seq_num = len(group_references)
            noteid = self.mknoteid(group, note_seq_num)
            refid = u'_r'+noteid

        a.text = u'%s %s' % (group, unicode(note_seq_num))
        a.text = u'[%s]' % a.text.strip()
        a.set('id', refid)
        a.set('href', '#')
        a.set('onClick',
              'return s(\'%s\')' % noteid)
        return SkipChildren(a)

    def xwriteReferenceList(self, t):
        if not self.references:
            return
        group = t.attributes.get('group', '')
        references = self.references.pop(group, [])
        if not references:
            return
        ol = ET.Element("ol")
        group_namedrefs = self.namedrefs.pop(group, {})
        for i, ref in enumerate(references):
            noteid = self.mknoteid(group, i+1)
            li = ET.SubElement(ol, "li", id=noteid)
            ref_name = ref.attributes.get('name')
            b = ET.SubElement(li, "b")
            b.tail = ' '

            if ref_name:
                ref_name = ref_name.replace(' ', '_')
                if not ref.children:
                    log.debug('No definition for named ref %r', ref_name)
                    #named reference has not been defined yet
                    #expect definition to be child of this reference list
                    matching_named_refs = [child for child in t.getAllChildren()
                                           if child.attributes.get('name', '').replace(' ', '_')
                                           == ref_name and child.children]
                    if matching_named_refs:
                        ref = matching_named_refs[0]
                        log.debug('Found defintion for named ref %r', ref_name)
                    else:
                        log.warn('Definition for named ref %r not found', ref_name)
                name_ref_count = group_namedrefs.get(ref_name, (None, 1))[1]
                if name_ref_count == 1:
                    ref_id = u'_r'+noteid+u'_'+unicode(0)
                    backref = ET.SubElement(b, 'a', href=u'#'+ref_id)
                    backref.set('onClick',
                                'return s(\'%s\')' % (ref_id))
                    backref.text = u'\u2191'
                else:
                    b.text = u'\u2191 '
                    backref_parent = ET.SubElement(b, 'sup')
                    for j in range(name_ref_count):
                        ref_id = u'_r'+noteid+u'_'+unicode(j)
                        backref = ET.SubElement(backref_parent, 'a', href=u'#'+ref_id)
                        backref.set('onClick',
                                    'return s(\'%s\')' % (ref_id))
                        backref.text = unicode(j+1)
                        backref.tail = ' '
            else:
                ref_id = u'_r'+noteid
                backref = ET.SubElement(b, 'a', href=u'#'+ref_id)
                backref.set('onClick',
                            'return s(\'%s\')' % (ref_id))
                backref.text = u'\u2191'
            self.writeChildren(ref, parent=li)
        return SkipChildren(ol)

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


def remove_childless_elements(element, parent=None):
    """
    Remove elements that are supposed to have children but are empty

    """   

    for child in element.getchildren()[:]:
        remove_childless_elements(child, element)

    if (element.tag.lower() not in ("br", "td", "img", "hr", "col", "colgroup") and
        not (element.getchildren() or element.text or element.tail) and parent):
        parent.remove(element)


def convert(obj, rtl=False):
    w = XHTMLWriter()
    e = w.write(obj)
    remove_childless_elements(e)
    if rtl:
        e.set("dir", "rtl")
    if w.languagelinks:
        languagelinks = [(obj.namespace, obj.target) for obj in w.languagelinks]
    else:
        languagelinks = []
    w.languagelinks = []
    text = ET.tostring(e, encoding='utf-8')
    return text, [], languagelinks
