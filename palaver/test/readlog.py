# Copyright (c) 2005 - 2007  OGG, LLC 
# See LICENSE.txt for details
import sys
import re
from datetime import datetime
from time import strptime
from twisted.words.xish import domish

class XmlParser(object):
    def __init__(self):
        self._reset()
    
    def parse(self, buf):
        self.stream.parse(buf)
        return self.entity
    
    def serialize(self, obj):
        if isinstance(obj, domish.Element):
            obj = obj.toXml()
            return obj
    
    def onDocumentStart(self, rootelem):
        self.entity = rootelem
    
    def onElement(self, element):
        if isinstance(element, domish.Element):
            self.entity.addChild(element)
        else:
            pass
    
    def _reset(self):
        # Setup the parser
        self.stream = domish.elementStream()
        self.stream.DocumentStartEvent = self.onDocumentStart
        self.stream.ElementEvent = self.onElement
        self.stream.DocumentEndEvent = self.onDocumentEnd
        self.entity = None
    
    def onDocumentEnd(self):
        pass

STANZA_RE = re.compile("^(<iq[^>]*/>|<iq.*?</iq>|<message[^>]*/>|<message.*?</message>|<presence[^>]*/>|<presence.*?</presence>)+$")

def get_stanzas(s):
    stanzas = []
    m = STANZA_RE.match(s)
    while m:
        stanzas.append(m.group(1))
        s = s[:-len(m.group(1))]
        m = STANZA_RE.match(s)
    stanzas.reverse()
    return stanzas
# TODO - need a way to configure for different log formats
XML_RE = re.compile("^(\d\d\d\d/\d\d/\d\d \d\d:\d\d) \w\w\w \[.*?\] (RECV|SEND): (((?:<iq[^>]*/>|<iq.*?</iq>|<message[^>]*/>|<message.*?</message>|<presence[^>]*/>|<presence.*?</presence>)+)(.*))$")

def readLog(f=sys.stdin, combine=False):
    for l in f.xreadlines():
        # check for send/recv lines
        m = XML_RE.match(l)
        if m:
            timestamp = datetime(*strptime(m.group(1), "%Y/%m/%d %H:%M")[0:6])

            typ = m.group(2)
            
            if m.group(5):
                print "GOT TRASH"
                # subtract out trash
                stanzas = get_stanzas(m.group(3)[:-len(m.group(5))])
            else:
                stanzas = get_stanzas(m.group(3))
            
            if combine:
                elems = []
                for g in stanzas:
                    p = XmlParser()
                    elems.append(p.parse(g))
                yield timestamp, typ, elems
            else:
                for g in stanzas:
                    p = XmlParser()
                    elem = p.parse(g)
                    yield timestamp, typ, elem


