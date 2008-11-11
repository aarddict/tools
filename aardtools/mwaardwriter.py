from mwlib import parser
from mwlib import cdbwiki, uparser, xhtmlwriter

def convert(obj):
    w = MWAardWriter()
    text = w._text(obj)
    return [text, w.tags]

class MWAardWriter(object):

    ignoreUnknownNodes = True
    namedLinkCount = 1

    def __init__(self):

        self.references = []
        
        self.errors = []
        self.languagelinks = []
        self.categorylinks = []
        
        self.tags = []
        self.current_list_number = 0 

    def _text(self, obj, offset=0):
        txt = ''
        start = offset
        if isinstance(obj, parser.Text):
            txt += obj.caption

        if isinstance(obj, parser.Ref):
            txt += obj.caption
            
        if isinstance(obj, parser.Paragraph):
            txt += '\n\n'
            
        if isinstance(obj, parser.ItemList):
            self.current_list_number = 0            
            
        if isinstance(obj, parser.Item):
            if (obj.parent.numbered):
                self.current_list_number += 1
                txt += ('%d. ' % self.current_list_number)
            else:
                txt += '\n* '

        if isinstance(obj, parser.Section):
            txt += '\n'
            start += 1
            self.tags.append(('h'+str(obj.level), start, start + len(self._text(obj.firstchild)), {}))

        if isinstance(obj, parser.Chapter):
            txt += '\n'
            start += 1
            self.tags.append(('h1', start, start + len(self._text(obj.caption)), {}))
                                    
        for c in obj:    
            txt += self._text(c, offset + len(txt)) 
        end = start + len(txt)
        
        if isinstance(obj, parser.Link):
            self.tags.append(('a', start, end, {'href':obj.target}))
        
        if isinstance(obj, parser.TagNode):
            if obj.caption == u'ref':
                print obj.caption
            self.tags.append((obj.caption, start, end, {}))

        if isinstance(obj, (parser.URL, parser.NamedURL)):
            if start == end:
                txt += obj.caption
                end = start + len(txt)
            self.tags.append(('a', start, end, {'href':obj.caption}))            
            
        if isinstance(obj, parser.Style):
            if obj.caption == "''":
                self.tags.append('i', start, end, {})
            if obj.caption == "'''":
                self.tags.append('b', start, end, {})
        
#        if not isinstance(obj, parser.Text):
#            tag = self._tag(obj, start, end)
#            if tag:
#                self.tags.append(tag)
#        #self.tags.append([obj.tag, start, end, dict(obj.attrib)])
#                
##        if element.tail:
##            txt += element.tail
        return txt
    
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
