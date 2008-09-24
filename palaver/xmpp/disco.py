# Copyright (c) 2005 Christopher Zorn, OGG, LLC 
# See LICENSE.txt for details
from twisted.words.xish import domish

from ns import *

class Feature(domish.Element):
    def __init__(self, feature):
        domish.Element.__init__(self, (DISCO_NS_INFO, 'feature'),
                                attribs={'var': feature})
class Identity(domish.Element):
    def __init__(self, category, type, name = None):
        domish.Element.__init__(self, (DISCO_NS_INFO, 'identity'),
                                attribs={'category': category,
                                         'type': type})
        if name:
            self['name'] = name



class Item(domish.Element):
    def __init__(self, jid, node = None, name = None, x = None):
        domish.Element.__init__(self, (DISCO_NS_ITEMS, 'item'),
                                attribs={'jid': jid})
        if node:
            self['node'] = unicode(node)

        if name:
            self['name'] = unicode(name)

        if x:
            self.addChild(x)

            
