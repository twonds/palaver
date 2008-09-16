# Copyright (c) 2005 Christopher Zorn, OGG, LLC 
# See LICENSE.txt for details
"""
 Stanzas and Namespaces for the jabber muc protocol
"""


"""
XMLNS
"""
NS_VERSION      = 'jabber:iq:version'

NS_COMPONENT    = 'jabber:component:accept'

NS_XMPP_STANZAS = 'urn:ietf:params:xml:ns:xmpp-stanzas'
NS_STANZAS      = NS_XMPP_STANZAS


NS_CLIENT       = 'jabber:client'
NS_X_DATA       = 'jabber:x:data'
NS_X_DELAY      = 'jabber:x:delay'

DISCO_NS        = 'http://jabber.org/protocol/disco'
DISCO_NS_INFO   = DISCO_NS + '#info'
DISCO_NS_ITEMS  = DISCO_NS + '#items'

NS_MUC          = 'http://jabber.org/protocol/muc'
NS_MUC_USER     = NS_MUC + '#user'
NS_MUC_ADMIN    = NS_MUC + '#admin'
NS_MUC_OWNER    = NS_MUC + '#owner'
NS_MUC_ROOMINFO = NS_MUC + '#roominfo'
NS_MUC_CONFIG   = NS_MUC + '#roomconfig'

NS_AD_HOC       = "http://jabber.org/protocol/commands"

"""
XMPP STANZAs
"""

MESSAGE   = '/message'
PRESENCE  = '/presence'


CHAT      = MESSAGE +'[@type="chat"]/body'
TCHAT     = MESSAGE +'[@type="chat"]'
GROUP_CHAT= MESSAGE +'[@type="groupchat"]'
MESSAGE_ERROR = MESSAGE +'[@type="error"]'

IQ        = '/iq'
IQ_GET    = IQ+'[@type="get"]'
IQ_SET    = IQ+'[@type="set"]'
IQ_RESULT = IQ+'[@type="result"]'
IQ_ERROR  = IQ+'[@type="error"]'
VERSION   = IQ_GET + '/query[@xmlns="' + NS_VERSION + '"]'

IQ_QUERY     = IQ+'/query'
IQ_GET_QUERY = IQ_GET + '/query'
IQ_SET_QUERY = IQ_SET + '/query'

IQ_COMMAND     = IQ+'/command'

MUC_ADMIN = IQ_QUERY+'[@xmlns="' + NS_MUC_ADMIN + '"]'
MUC_OWNER = IQ_QUERY+'[@xmlns="' + NS_MUC_OWNER + '"]'

MUC_AO = MUC_ADMIN + '|' + MUC_OWNER

DISCO_INFO = IQ_GET + '/query[@xmlns="' + DISCO_NS_INFO + '"]'
DISCO_ITEMS = IQ_GET + '/query[@xmlns="' + DISCO_NS_ITEMS + '"]'
DISCO_PUB_ITEMS = IQ_SET + '/query[@xmlns="' + DISCO_NS_ITEMS + '"]'


"""
ERRORS
"""

AUTH_ERROR   = '/error[@type="auth"]'
MODIFY_ERROR = '/error[@type="modify"]'
WAIT_ERROR   = '/error[@type="wait"]'
CANCEL_ERROR = '/error[@type="cancel"]'


"""
Some element classes and utitlity functions
"""

from twisted.words.xish import domish

    

def getresource(user):
    try:
        return str(user).split("/",1)[1]
    except:
        return user

def uriCheck(elem, uri):
    if str(elem.toXml()).find('xmlns') == -1:
        elem['xmlns'] = uri


class X(domish.Element):
    def __init__(self, typ = 'result', title = None, instructions = None, fields = None):
        domish.Element.__init__(self, (NS_X_DATA, 'x'),
                                attribs={'type': typ})

        uriCheck(self, NS_X_DATA)
        if title:
            self.addElement('title', None, title)

        if instructions:
            self.addElement('instructions', None, instructions)
            
        for f in fields:
            field = self.addElement('field')
            if f.has_key('type'):
                field['type'] = f['type']
            if f.has_key('var'):
                field['var'] = f['var']
            if f.has_key('label'):
                field['label'] = f['label']

            if f.has_key('options'):
                for o in f['options']:
                    option = field.addElement('option')
                    if o.has_key('label'):
                        option['label'] = o['label']
                    if o.has_key('value'):
                        option.addElement('value', None,o['value'])
            if f.has_key('value'):
                field.addElement('value', None,f['value'])
            
