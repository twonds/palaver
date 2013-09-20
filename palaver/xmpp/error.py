# Copyright (c) 2005-2013 Christopher Zorn
# See LICENSE.txt for details

from ns import *
from palaver import groupchat

class Error(Exception):
    muc_error = None
    stanza_error = None
    msg = ''

class RoomNotFound(Error):
    stanza_error = 'not-found'

class JidMalformed(Error):
    stanza_error = 'jid-malformed'

class NotImplemented(Error):
    stanza_error = 'feature-not-implemented'

class BadRequest(Error):
    stanza_error = 'bad-request'


error_map = {
    groupchat.RoomNotFound: ('item-not-found', None),
    groupchat.RoomExists: ('conflict', None),
    groupchat.NickConflict: ('conflict', None),
    groupchat.BadRequest: ('bad-request',None),
    groupchat.NotAuthorized: ('not-authorized', None),
    groupchat.Forbidden: ('forbidden', None),
    groupchat.NotAllowed: ('not-allowed', None),
    groupchat.NotMember: ('registration-required', None),
    groupchat.Unavailable: ('service-unavailable', None),
    groupchat.InvalidConfigurationOption: ('not-acceptable', None),
    groupchat.InvalidConfigurationValue: ('not-acceptable', None),
}

conditions = {
	'bad-request':		        {'code': '400', 'type': 'modify'},
        'jid-malformed':	        {'code': '400', 'type': 'modify'},
	'not-authorized':	        {'code': '401', 'type': 'auth'},
        'forbidden':  	                {'code': '403', 'type': 'auth'},
	'item-not-found':	        {'code': '404', 'type': 'cancel'},
        'not-allowed':	                {'code': '405', 'type': 'cancel'},
	'not-acceptable':	        {'code': '406', 'type': 'modify'},
        'registration-required':        {'code': '407', 'type': 'auth'},
	'conflict':		        {'code': '409', 'type': 'cancel'},
	'internal-server-error':	{'code': '500', 'type': 'wait'},
	'feature-not-implemented':	{'code': '501', 'type': 'cancel'},
	'service-unavailable':		{'code': '503', 'type': 'cancel'},
}

def error_from_iq(iq, condition, text = '', type = None):
    if not iq.hasAttribute('from'):
        return
    iq.swapAttributeValues("to", "from")
    iq["type"] = 'error'
    e = iq.addElement("error")
    
    c = e.addElement((NS_XMPP_STANZAS, condition), NS_XMPP_STANZAS)
    
    if type == None:
        type = conditions[condition]['type']

    code = conditions[condition]['code']
    
    e["code"] = code
    e["type"] = type

    if text:
        t = e.addElement((NS_XMPP_STANZAS, "text"), NS_XMPP_STANZAS, text)

    return iq
    

def error_from_message(message, condition, text = '', type = None):
    message.swapAttributeValues("to", "from")
    message["type"] = 'error'
    e = message.addElement("error")
        
    c = e.addElement((NS_XMPP_STANZAS, condition), NS_XMPP_STANZAS)

    if type == None:
        type = conditions[condition]['type']

    code = conditions[condition]['code']

    e["code"] = code
    e["type"] = type
    
    if text:
        t = e.addElement((NS_XMPP_STANZAS, "text"), NS_XMPP_STANZAS, text)

    return message


def error_from_presence(presence, condition, text = '', type = None):
    presence.swapAttributeValues("to", "from")
    presence['type'] = 'error'
    e = presence.addElement("error")
    
    c = e.addElement((NS_XMPP_STANZAS, condition), NS_XMPP_STANZAS)

    if type == None:
        type = conditions[condition]['type']

    code = conditions[condition]['code']

    e["code"] = code
    e["type"] = type

    if text:
        t = e.addElement((NS_XMPP_STANZAS, "text"), NS_XMPP_STANZAS, text)

    return presence
