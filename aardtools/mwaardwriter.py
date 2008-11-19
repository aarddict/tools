import logging
from collections import defaultdict

EXCLUDE_TABLE_CLASSES = set(('navbox', 'collapsible', 'autocollapse'))

def convert(obj):
    w = MWAardWriter()
    text, tags = w.txt(obj)
    return text, tags

def newline(func):
    def f(*args, **kwargs):
        txt, tags = func(*args, **kwargs)
        if not txt.endswith(u'\n'):
            txt += u'\n'
        return txt, tags
    f.__name__ = func.__name__
    f.__doc__ = func.__doc__
    return f

class MWAardWriter(object):

    def __init__(self):
        self.refgroups = defaultdict(list)        
        self.errors = []
        self.languagelinks = []
        self.categorylinks = []        
        self.current_list_number = 0
        self.current_tables = []
        
    def _Text(self, obj):
        return obj.caption, []

    @newline
    def _ItemList(self, obj):
        self.current_list_number = 0
        return self.process_children(obj)
    
    @newline
    def _Item(self, obj):
        txt = u''        
        if (obj.parent.numbered):
            self.current_list_number += 1
            txt += u'%d. ' % self.current_list_number
        else:
            txt += u'\u2022 '
        return self.process_children(obj, txt)        
    
    @newline
    def _Paragraph(self, obj):
        txt, tags = self.process_children(obj)
        tags.append((u'p', 0, len(txt), {}))
        return txt, tags        
    
    @newline
    def _Section(self, obj):
        level = 2 + obj.getLevel() # starting with h2
        h = u'h%d' % level
        txt, tags = self.txt(obj.children[0])
        tags.append((h, 0, len(txt), {}))
        txt += u'\n'
        obj.children = obj.children[1:]
        return self.process_children(obj, txt, tags)

    @newline
    def _Chapter(self, obj):
        txt = obj.caption
        tags = [(u'h1', 0, len(txt), {})]
        return txt, tags
    
    def _CategoryLink(self, obj):
        self.categorylinks.append(obj.target)
        return u'', []

    def _LangLink(self, obj):
        self.languagelinks.append((obj.namespace, obj.target))
        return u'', []
    
    def _ArticleLink(self, obj):
        txt, tags = self.process_children(obj)
        if not txt:
            txt = obj.caption
        tags.append((u'a', 0, len(txt), {u'href':obj.target}))
        return txt, tags
    
    _InterwikiLink = _ArticleLink       
    
    def _NamedURL(self, obj):
        txt, tags = self.process_children(obj)
        if not txt:
            txt = obj.caption        
        tags.append((u'a', 0, len(txt), {u'href':obj.caption}))
        return txt, tags

    def _URL(self, obj):
        txt, tags = self.process_children(obj)
        if not txt:
            txt = obj.caption
        tags.append((u'a', 0, len(txt), {u'href':obj.caption}))
        return txt, tags
    
    def _Style(self, obj):
        txt, tags = self.process_children(obj)
        if obj.caption == "''":
            tags.append((u'i', 0, len(txt), {}))
        elif obj.caption == "'''":
            tags.append((u'b', 0, len(txt), {}))
        elif obj.caption == ";":
            tags.append((u'tt', 0, len(txt), {}))            
        return tags                

    def _TagNode(self, obj):
        txt, tags = self.process_children(obj)
        tagname = obj.caption
        tags.append((tagname, 0, len(txt), {}))
        return txt, tags        

    def _Node(self, obj):
        txt, tags = self.process_children(obj)
        tagname = obj._tag if hasattr(obj, '_tag') else obj.caption
        if tagname:
            tags.append((tagname, 0, len(txt), obj.attributes))
        return txt, tags        
    
    def _ImageLink(self, obj):
        return '', []
    
    @newline
    def _BreakingReturn(self, obj):
        return '', []
    
    def _Generic(self, obj):
        txt, tags = self.process_children(obj)
        tagname = obj._tag
        tags.append((tagname, 0, len(txt), obj.attributes))
        return txt, tags    
    
    _Emphasized = _Strong = _Small = _Big = _Cite = _Sub = _Sup = _Generic
    
    _Div = newline(_Generic)
    
    def add_ref(self, obj):
        name = obj.attributes.get(u'name', '')        
        group = obj.attributes.get(u'group', '')
        
        references = self.refgroups[group]
        
        refid = None
        
        if name:        
            existing = [r for r in references 
                        if name == r.attributes.get(u'name', '')]
            if existing:
                refid = references.index(existing[0])
                
        if refid is None:        
            references.append(obj)
            refid = len(references)
        return refid, name, group
            
    def _Reference(self, obj):        
        refid, name, group = self.add_ref(obj)
        refidstr = unicode(refid)
        txt = u'%s %s' % (group, refidstr)
        txt = u'[%s]' % txt.strip()
        return txt, [(u'ref', 0, len(txt), {u'id': refidstr, u'group': group})]
    
    @newline
    def _ReferenceList(self, obj):
        group = obj.attributes.get(u'group', '')
        tags = []
        txt = u''
        for i, refobj in enumerate(self.refgroups[group]):            
            start = len(txt)
            txt += u'%s. ' % unicode(i+1)
            txt, tags = self.process_children(refobj, txt, tags)
            end = len(txt)
            txt += u'\n'
            tags.append((u'note', start, end, 
                         {u'id': unicode(i+1), u'group': group}))
        del self.refgroups[group]
        return txt, tags            
    
    def _Article(self, a):
        # add article name as first section heading
        txt = a.caption
        tags = [(u'h1', 0, len(txt), {})]
        txt += u'\n'
        return self.process_children(a, txt, tags)        
    
    def _Cell(self, obj):
        current_table, current_row = self.current_tables[-1]
        if current_row is None:            
            logging.warn("Can't add cell outside of row")
        else:                       
            txt, tags = self.process_children(obj)
            tags.append((u'cell', 0, len(txt), obj.attributes))
            current_row.append((txt, tags))
        return '', []

    def _Row(self, obj):            
        current_table, current_row = self.current_tables[-1]
        if current_row is not None:
            logging.error('Processing row is already in progress')
        else:            
            self.current_tables[-1] = (current_table, [])              
            self.process_children(obj)
            current_table, current_row = self.current_tables[-1]
            current_table.append((current_row, obj.attributes))
            self.current_tables[-1] = (current_table, None)                
        return '', []
    
    @newline
    def _Table(self, obj):
        tableclasses = obj.attributes.get('class', '').split()
        if any((tableclass in EXCLUDE_TABLE_CLASSES 
                for tableclass in tableclasses)):
            return '', []
        
        self.current_tables.append(([], None))
        
        self.process_children(obj)
        current_table, current_row = self.current_tables[-1]
        tags = [('table', 0, 1, {'rows': current_table, 
                                 'attrs': obj.attributes})]        
        self.current_tables.pop()
        return ' ', tags
        
    def apply_offset(self, tags, offset):
        return [(name, start+offset, end+offset, attrs) 
                for name, start, end, attrs in tags]        
        
    def txt(self, obj):
        m = "_" + obj.__class__.__name__
        m = getattr(self, m, None)
        if m: # find handler
            return m(obj)
        else:
            logging.debug('No handler for %s, write children', obj)
            return self.process_children(obj)
                
    def process_children(self, obj, txt=u'', tags=None):
        if tags is None:
            tags = []
        else:
            tags = tags[:]
        for c in obj:
            ctxt, ctags = self.txt(c)
            tags += self.apply_offset(ctags, len(txt))
            txt += ctxt            
        logging.debug('Processed children for %s, returning %s with tags %s', obj, txt, tags)
        return txt, tags                
        

#    def _tag(self, obj, start, end):
#        m = "xtag" + obj.__class__.__name__
#        m=getattr(self, m, None)
#        if m: # find handler
#            return m(obj)
#        elif self.ignoreUnknownNodes:
#            logging.debug("%s starting at %d ending at %d was skipped", obj, start, end)
#            return None
#        else:
#            raise Exception("unknown node:%r" % obj)

                    
#    def asstring(self):
#        def _r(obj, p=None):
#            for c in obj:
#                assert c is not None
#                for k,v in c.items():
#                    if v is None:
#                        print k,v
#                        assert v is not None
#                _r(c,obj)
#        _r(self.root)
#        #res = self.header + ET.tostring(self.getTree())
#        res = self.header + ET.tostring(self.root)
#        return res
    
#    def writeText(self, obj, parent):
#        if parent.getchildren(): # add to tail of last tag
#            t = parent.getchildren()[-1]
#            if not t.tail:
#                t.tail = obj.caption
#            else:
#                t.tail += obj.caption
#        else:
#            if not parent.text:
#                parent.text = obj.caption
#            else:
#                parent.text += obj.caption
#
#    def writedebug(self, obj, parent, comment=""):
#        if not self.debug or parent is None:
#            return 
#        attrs = obj.__dict__.keys()
#        stuff =  ["%s : %r" %(k,getattr(obj,k)) for k in attrs if 
#                  (not k in ("_parentref", "children")) and getattr(obj,k)
#                  ]
#        text = obj.__class__.__name__  + repr(stuff) 
#        if comment:
#            text += "\n" + comment
#        parent.append(ET.Comment(text.replace("--", " - - "))) # FIXME (hot fix)
#
#
#    def writeparsetree(self, tree):
#        out = StringIO.StringIO()
#        parser.show(out, tree)
#        self.root.append(ET.Comment(out.getvalue().replace("--", " - - ")))
#        
#
#    def write(self, obj, parent=None):
#        # if its text, append to last node
#        if isinstance(obj, parser.Text):
#            self.writeText(obj, parent)
#        else:
#            self.writedebug(obj, parent)
#            # check for method
#            m = "xwrite" + obj.__class__.__name__
#            m=getattr(self, m, None)
#            if m: # find handler
#                e = m(obj)
#            elif self.ignoreUnknownNodes:
#                self.writedebug(obj, parent, "was skipped")
#                log("SKIPPED")
#                showNode(obj)
#                e = None
#            else:
#                raise Exception("unknown node:%r" % obj)
#            
#            if isinstance(e, SkipChildren): # do not process children of this node
#                return e.element
#            elif e is None:
#                e = parent
#
#            for c in obj.children[:]:
#                ce = self.write(c,e)
#                if ce is not None and ce is not e:                    
#                    e.append(ce)
#            return e
#
#    def writeChildren(self, obj, parent): # use this to avoid bugs!
#        "writes only the children of a node"
#        for c in obj:                    
#            res = self.write(c, parent)
#            if res is not None and res is not parent:
#                parent.append(res)
#
#    def writeBook(self, book, output=None):
#        self.xmlbody.append(self.write(book))
#        #self.write(book, self.xmlbody)
#        if output:
#            open(output, "w").write(self.text)
#
#    def xwriteBook(self, obj):
#        e = ET.Element("div")
#        e.set("class", "mwx.collection")
#        return e # do not return an empty top level element
#
#    def xwriteArticle(self, a):
#        # add article name as first section heading
#        print "in write Article", a
#        e = ET.Element("div")
#        e.set("class", "mwx.article")
#        h = ET.SubElement(e, "h1")
#        h.text = a.caption
#        self.writeChildren(a, e)
#        for x in (self.writeCategoryLinks(), self.writeLanguageLinks()):
#            if x is not None:
#                e.append(x)
#        return SkipChildren(e)
#
#
#    def xwriteChapter(self, obj):
#        e = ET.Element("div")
#        e.set("class", "mwx.chapter")
#        h = ET.SubElement(e, "h1")
#        self.write(obj.caption)
#        return e
#
#
#    def xwriteSection(self, obj):
#        e = ET.Element("div")
#        e.set("class", "mwx.section")
#        level = 2 + obj.getLevel() # starting with h2
#        h = ET.SubElement(e, "h%d" % level)
#        self.write(obj.children[0], h)
#        obj.children = obj.children[1:]
#        return e
#
#        
#    def xwriteNode(self, n):
#        pass # simply write children
#
#
#    def xwriteCell(self, cell):
#        td = ET.Element("td")
#        setVList(td, cell)           
#        return td
#            
#    def xwriteRow(self, row):
#        return ET.Element("tr")
#
#    def xwriteTable(self, t):           
#        table = ET.Element("table")
#        setVList(table, t)           
#        if t.caption:
#            c = ET.SubElement(table, "caption")
#            self.writeText(t.caption, c)
#        return table
#
#
#
#
#    # Special Objects
#
#
#    def xwriteTimeline(self, obj): 
#        s = ET.Element("object")
#        s.set("class", "mwx.timeline")
#        s.set("type", "application/mediawiki-timeline")
#        s.set("src", "data:text/plain;charset=utf-8,%s" % obj.caption)
#        em = ET.SubElement(s, "em")
#        em.set("class", "mwx.timeline.alternate")
#        em.text = u"Timeline"
#        return s
#
#    def xwriteHiero(self, obj): # FIXME parser support
#        s = ET.Element("object")
#        s.set("class", "mwx.hiero")
#        s.set("type", "application/mediawiki-hiero")
#        s.set("src", "data:text/plain;charset=utf-8,%s" % obj.caption)
#        em = ET.SubElement(s, "em")
#        em.set("class", "mwx.hiero.alternate")
#        em.text = u"Hiero"
#        return s
#
#
#    def xwriteMath(self, obj):
#        return writerbase.renderMath(obj.caption, output_mode='mathml', render_engine='blahtexml')
#
#    def xwriteMath_WITH_OBJECT(self, obj): 
#        """
#        this won't validate as long as we are using xhtml 1.0 transitional
#
#        see also: http://www.mozilla.org/projects/mathml/authoring.html
#        """
#        s = ET.Element("object")
#        s.set("class", "mwx.math")
#        s.set("type", "application/x-latex")
#        s.set("src", "data:text/plain;charset=utf-8,%s" % obj.caption)
#        r = writerbase.renderMath(obj.caption, output_mode='mathml', render_engine='blahtexml')
#        if not r:
#            #r = ET.Element("em")
#            #r.set("class", "math.error")
#            #r.text = obj.caption
#            pass
#        else:
#            assert r is not None
#            s.append(r)
#        return s
#
#
#    # Links ---------------------------------------------------------
#
#
#    def xwriteLink(self, obj): # FIXME (known|unknown)
#        a = ET.Element("a", href=obj.url or "#")
#        a.set("class", "mwx.link.article")
#        if not obj.children:
#            a.text = obj.target
#        return a
#
#    xwriteArticleLink = xwriteLink
#    xwriteInterwikiLink = xwriteLink
#    xwriteNamespaceLink = xwriteLink
#
#
#    def xwriteURL(self, obj):
#        a = ET.Element("a", href=obj.caption)
#        a.set("class", "mwx.link.external")
#        if not obj.children:
#            a.text = obj.caption
#        return a
#
#    def xwriteNamedURL(self, obj):
#        a = ET.Element("a", href=obj.caption)
#        a.set("class", "mwx.link.external")
#        if not obj.children:
#            name = "[%s]" % self.namedLinkCount
#            self.namedLinkCount += 1
#            a.text = name
#        return a
#
#
#    def xwriteSpecialLink(self, obj): # whats that?
#        a = ET.Element("a", href=obj.url or "#")
#        a.set("class", "mwx.link.special")
#        if not obj.children:
#            a.text = obj.target
#        return a
#
#       
#    def xwriteImageLink(self, obj): 
#        if obj.caption or obj.align:
#            #assert not obj.isInline() and not obj.thumb
#            e = ET.Element("div")
#            e.set("class", "mwx.image.float")
#            if obj.align:
#                e.set("align", obj.align)
#            if obj.caption:
#                e.text = obj.caption            
#        else:
#            e = ET.Element("span")
#            if obj.isInline():
#                e.set("class", "mwx.image.inline")
#            if obj.thumb:
#                e.set("class", "mwx.image.thumb")
#
#        href ="Image:" + obj.target 
#        e = ET.SubElement(e, "a", href=href)
#        e.set("class", "mwx.link.image")
#
#        # use a resolver which redirects to the real image
#        # e.g. "http://anyhost/redir?img=IMAGENAME"
#        if self.imagesrcresolver:
#            imgsrc = self.imagesrcresolver.replace("IMAGENAME", obj.target)
#        elif self.environment and self.environment.images:
#            imgsrc = self.environment.images.getURL(obj.target, obj.width or None)
#        else:
#            imgsrc = obj.target
#
#        if not imgsrc:
#            return None
#
#        img = ET.SubElement(e, "img", src=imgsrc, alt="") 
#        if obj.width:
#            img.set("width", unicode(obj.width))
#        if obj.height:
#            img.set("height", unicode(obj.height))
#        return e 
#
#    def xwriteImageMap(self, obj): # FIXME!
#        if obj.imagemap.imagelink:
#            return self.write(obj.imagemap.imagelink)
#
#
#    def xwriteGallery(self, obj):
#        s = ET.Element("div")
#        s.set("class", "mwx.gallery")
#        setVList(s, obj)
#        return s
#
## -------------- things that are collected --------------
#
#
#    def xwriteCategoryLink(self, obj):
#        if obj.target:
#            self.categorylinks.append(obj)
#        return SkipChildren()
#
#    def writeCategoryLinks(self):       
#        seen = set()
#        if not self.categorylinks:
#            return
#        ol = ET.Element("ol")
#        ol.set("class", "mwx.categorylinks")
#        for i,link in enumerate(self.categorylinks):
#            if link.target in seen:
#                continue
#            seen.add(link.target)
#            li = ET.SubElement(ol, "li")
#            a = ET.SubElement(li, "a", href=link.target)
#            a.set("class", "mwx.link.category")
#            if not link.children:
#                a.text = link.target
#            else:
#                self.writeChildren(link, parent=a)
#        self.categorylinks = []
#        return ol
#
#
#    def xwriteLangLink(self, obj): # FIXME no valid url (but uri)
#        if obj.target:
#            self.languagelinks.append(obj)
#        return SkipChildren()
#
#    def writeLanguageLinks(self):
#        if not self.languagelinks:
#            return
#        ol = ET.Element("ol")
#        ol.set("class", "mwx.languagelinks")
#        for i,link in enumerate(self.languagelinks):
#            li = ET.SubElement(ol, "li")
#            a = ET.SubElement(li, "a", href=link.target)
#            a.set("class", "mwx.link.interwiki")
#            if not link.children:
#                a.text = link.target
#            else:
#                self.writeChildren(link, parent=a)
#        self.languagelinks = []
#        return ol
#
#
#        
#    def xwriteReference(self, t):
#        assert t is not None
#        self.references.append(t)
#        t =  ET.Element("sup")
#        t.set("class", "mwx.reference")
#        t.text = unicode( len(self.references))
#        return SkipChildren(t)
#
#        
#    def xwriteReferenceList(self, t):
#        if not self.references:
#            return
#        ol = ET.Element("ol")
#        ol.set("class", "mwx.references")
#        for i,ref in enumerate(self.references):
#            li = ET.SubElement(ol, "li", id="cite_note-%s" % i)
#            self.writeChildren(ref, parent=li)
#        self.references = []            
#        return ol
#
#    
#    # ---------- Generic XHTML Elements --------------------------------
#
#    def xwriteGenericElement(self, t):
#        if not hasattr(t, "starttext"):
#            if hasattr(t, "_tag"):
#                e = ET.Element(t._tag)
#                setVList(e, t)
#                return e
#            else:
#                log("skipping %r"%t)
#                return
#        else: 
#            # parse html and return ET elements
#            stuff = t.starttext + t.endtext
#            try:
#                if not t.endtext and not "/" in t.starttext:
#                    stuff = t.starttext[:-1] + "/>"
#                p =  ET.fromstring(stuff)
#            except Exception, e:
#                log("failed to parse %r \n" % t)
#                parser.show(sys.stdout, t)
#                #raise e
#                p = None
#        return p
#
#    xwriteEmphasized = xwriteGenericElement
#    xwriteStrong = xwriteGenericElement
#    xwriteSmall = xwriteGenericElement
#    xwriteBig = xwriteGenericElement
#    xwriteCite = xwriteGenericElement
#    xwriteSub = xwriteGenericElement
#    xwriteSup = xwriteGenericElement
#    xwriteCode = xwriteGenericElement
#    xwriteBreakingReturn = xwriteGenericElement
#    xwriteHorizontalRule = xwriteGenericElement
#    xwriteTeletyped = xwriteGenericElement
#    xwriteDiv = xwriteGenericElement
#    xwriteSpan = xwriteGenericElement
#    xwriteVar= xwriteGenericElement
#    xwriteRuby = xwriteGenericElement
#    xwriteRubyBase = xwriteGenericElement
#    xwriteRubyParentheses = xwriteGenericElement
#    xwriteRubyText = xwriteGenericElement
#    xwriteDeleted = xwriteGenericElement
#    xwriteInserted = xwriteGenericElement
#    xwriteTableCaption = xwriteGenericElement
#    xwriteDefinitionList = xwriteGenericElement
#    xwriteDefinitionTerm = xwriteGenericElement
#    xwriteDefinitionDescription = xwriteGenericElement
#
#    def xwritePreFormatted(self, n):
#        return ET.Element("pre")
#
#    def xwriteParagraph(self, obj):
#        """
#        currently the parser encapsulates almost anything into paragraphs, 
#        but XHTML1.0 allows no block elements in paragraphs.
#        therefore we use the html-div-element. 
#
#        this is a hack to let created documents pass the validation test.
#        """
#        e = ET.Element(self.paratag) # "div" or "p"
#        e.set("class", "mwx.paragraph")
#        return e
#
#
#    # others: Index, Gallery, ImageMap  FIXME
#    # see http://meta.wikimedia.org/wiki/Help:HTML_in_wikitext
#
#    # ------- TAG nodes (deprecated) ----------------
#
#    def xwriteOverline(self, s):
#        e = ET.Element("span")
#        e.set("class", "mwx.style.overline")
#        return e    
#
#    def xwriteUnderline(self, s):
#        e = ET.Element("span")
#        e.set("class", "mwx.style.underline")
#        return e
#
#    def xwriteSource(self, s):       
#        # do we have a lang attribute here?
#        e = ET.Element("code")
#        e.set("class", "mwx.source")
#        return e
#    
#    def xwriteCenter(self, s):
#        e = ET.Element("span")
#        e.set("class", "mwx.style.center")
#        return e
#
#    def xwriteStrike(self, s):
#        e = ET.Element("span")
#        e.set("class", "mwx.style.strike")
#        return e
#
#    def _xwriteBlockquote(self, s, klass): 
#        e = ET.Element("blockquote")
#        e.set("class", klass)
#        level = len(s.caption) # FIXME
#        return e
#    
#    def xwriteBlockquote(self, s):
#        "margin to the left & right"
#        return self._xwriteBlockquote(s, klass="mwx.blockquote")
#
#    def xwriteIndented(self, s):
#        "margin to the left"
#        return self._xwriteBlockquote(s, klass="mwx.indented")
#
#    def xwriteItem(self, item):
#        return ET.Element("li")
#
#    def xwriteItemList(self, lst):
#        if lst.numbered:
#            tag = "ol"
#        else:
#            tag = "ul"
#        return ET.Element(tag)
