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
        txt = txt.rstrip() + u'\n'
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
        tags.append(maketag(u'p', txt, obj.attributes))
        return txt, tags        
    
    @newline
    def _Section(self, obj):
        level = 2 + obj.getLevel() # starting with h2
        h = u'h%d' % level
        txt, tags = self.txt(obj.children[0])
        tags.append(maketag(h, txt))
        txt += u'\n'
        obj.children = obj.children[1:]
        return self.process_children(obj, txt, tags)

    @newline
    def _Chapter(self, obj):
        txt = obj.caption
        tags = [maketag(u'h1', txt)]
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
        tags.append(maketag(u'a', txt, {u'href':obj.target}))
        return txt, tags
    
    _InterwikiLink = _ArticleLink       
    
    def _NamedURL(self, obj):
        txt, tags = self.process_children(obj)
        if not txt:
            txt = obj.caption        
        tags.append(maketag(u'a', txt, {u'href':obj.caption}))
        return txt, tags

    def _URL(self, obj):
        txt, tags = self.process_children(obj)
        if not txt:
            txt = obj.caption
        tags.append(maketag(u'a', txt, {u'href':obj.caption}))
        return txt, tags
    
    def _Style(self, obj):
        txt, tags = self.process_children(obj)
        if obj.caption == "''":
            tags.append(maketag(u'i', txt))
        elif obj.caption == "'''":
            tags.append(maketag(u'b', txt))
        elif obj.caption == ";":
            tags.append(maketag(u'tt', txt))            
        return tags                

    def _TagNode(self, obj):
        txt, tags = self.process_children(obj)
        tagname = obj.caption
        tags.append(maketag(tagname, txt, obj.attributes))
        return txt, tags        

    def _Node(self, obj):
        txt, tags = self.process_children(obj)
        tagname = obj._tag if hasattr(obj, '_tag') else obj.caption
        if tagname:
            tags.append(maketag(tagname, txt, obj.attributes))
        return txt, tags        
    
    def _ImageLink(self, obj):
        return '', []
    
    @newline
    def _BreakingReturn(self, obj):
        return '', []
    
    def _Generic(self, obj):
        txt, tags = self.process_children(obj)
        tagname = obj._tag
        tags.append(maketag(tagname, txt, obj.attributes))
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
        return txt, [maketag(u'ref', txt, {u'id': refidstr, 
                                           u'group': group})]
    
    @newline
    def _ReferenceList(self, obj):
        group = obj.attributes.get(u'group', '')
        tags = []
        txt = u''
        for i, refobj in enumerate(self.refgroups[group]):            
            start = len(txt)
            txt += u'%s. ' % unicode(i+1)
            txt, tags = self.process_children(refobj, txt, tags)
            tags.append(maketag(u'note', txt,  {u'id': unicode(i+1), 
                                                u'group': group}, 
                                start=start))
            txt += u'\n'
        del self.refgroups[group]
        return txt, tags            
    
    def _Article(self, a):
        # add article name as first section heading
        txt = a.caption
        tags = [maketag(u'h1', txt)]
        txt += u'\n'
        return self.process_children(a, txt, tags)        
    
    def _Cell(self, obj):
        current_table, current_row = self.current_tables[-1]
        if current_row is None:            
            logging.warn("Can't add cell outside of row")
        else:                       
            txt, tags = self.process_children(obj)
            tags.append(maketag(u'td', obj.attributes))
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
        
    def _Table(self, obj):
        tableclasses = obj.attributes.get('class', '').split()
        if any((tableclass in EXCLUDE_TABLE_CLASSES 
                for tableclass in tableclasses)):
            return '', []
        
        self.current_tables.append(([], None))
        
        self.process_children(obj)
        current_table, current_row = self.current_tables[-1]
        txt = u' '
        tags = [maketag('tbl', txt, {u'rows': current_table, 
                                     u'attrs': obj.attributes})]        
        self.current_tables.pop()
        return txt+u'\n', tags
        
    def apply_offset(self, tag, offset):
        mtag = list(tag)
        mtag[1] += offset
        mtag[2] += offset
        return tuple(mtag)
        
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
            txtlen = len(txt)
            tags += [self.apply_offset(ctag, txtlen) for ctag in ctags]
            txt += ctxt            
        logging.debug('Processed children for %s, returning %s with tags %s', 
                      obj, txt, tags)
        return txt, tags                

def maketag(name, txt, attrs=None, start=0):
    end = len(txt)
    return (name, start, end, attrs) if attrs else (name, start, end) 
