# -*- coding: utf-8 -*-
# MUC component service.
#
# Copyright (c) 2005-2013 Christopher Zorn
# See LICENSE.txt for details

from twisted.words.protocols.jabber import jid, xmlstream
from twisted.internet import defer
from twisted.python import components, log
from twisted.words.xish import domish

try:
    from twisted.words.protocols.jabber.component import IService
except:
    from twisted.words.protocols.jabber.ijabber import IService
from twisted.words.protocols.jabber import component

from zope.interface import implements

import datetime

from xmpp.ns import *
from xmpp.error import *
from xmpp import disco
from xmpp import jid_escape, jid_unescape

import types
import groupchat

def getCData(elem):
    for n in elem.children:
        if isinstance(n, types.StringTypes): return n
    return ""

def _internJIDToFrom(elem):
    jidTo = jid.internJID(elem['to'])
    jidFrom = jid.internJID(elem['from'])
    return jidTo, jidFrom


class StzCache:
    """
    A class to serialize and cache a common stanza being broadcasted to many entities.
    """

    def __init__(self):
        self.stzs = {}
        self._id_counter = 0

    def getKey(self):
        # create a key
        self._id_counter += 1
        return str(self._id_counter)

    def isCached(self, key):
        return self.stzs.has_key(key)

    def stop(self, key):
        if self.stzs.has_key(key):
            del self.stzs[key]

    def start(self, key, obj, attr, val):
        """
        Set up the serialized string we are caching.
        """
        obj[attr] = '%s'
        self.stzs[key] = obj.toXml()
        return self.serialize(key, val)

    def serialize(self, key, val):
        if not self.stzs.has_key(key):
            return ''
        try:
            ret_str = self.stzs[key].replace("'%s'", u"'%s'" % (val,), 1)
            return ret_str
        except:
            log.err()
            log.msg(self.stzs[key])
            return ''

class Service(component.Service):

    implements(IService)

    def __init__(self, groupchat, logger=None):
        self.groupchat = groupchat
        self.logger = logger
        self.error_list = []
        self.stz_cache = StzCache()

    def error(self, failure, stanza):
        frm  = None
        room = None
        try:
            room = jid.internJID(stanza['to']).user
            frm  = stanza.getAttribute('from')
        except:
            log.err()

        if '_delStzPending' in dir(self):
            self._delStzPending(jid_unescape(room), frm)

        try:
            e = failure.trap(Error, *error_map.keys())
        except:
            failure.printBriefTraceback()
            stanza_error = 'internal-server-error'
            try:
                msg = failure.value.msg
            except:
                msg = ''

            if stanza.name == 'iq':
                error_from_iq(stanza, stanza_error, msg)
            if stanza.name == 'message':
                error_from_message(stanza, stanza_error, msg)
            if stanza.name == 'presence':
                error_from_presence(stanza, stanza_error, msg)
            return stanza
        else:
            if e == Error:
                stanza_error = failure.value.stanza_error
                muc_error    = failure.value.muc_error
                msg = ''
            else:
                stanza_error, muc_error = error_map[e]
                msg = failure.value.msg
            if stanza.name == 'iq':
                error_from_iq(stanza, stanza_error, msg)
            elif stanza.name == 'message':
                error_from_message(stanza, stanza_error, msg)
                self.send(stanza)
                return
            elif stanza.name == 'presence':
                error_from_presence(stanza, stanza_error, msg)
                self.send(stanza)
                return
            else:
                log.msg(str(failure))

            return stanza

    def success(self, result, iq):
        if not iq.hasAttribute("from"):
            log.err('Strange bug on success')
            return

        iq.swapAttributeValues("to", "from")
        iq["type"] = 'result'
        q = getattr(iq, 'query', None)
        if q:
            q.children = []

            if len(result)>0:
                for child in result:
                    if isinstance(child, domish.Element):
                        q.addChild(child)
                    else:
                        log.msg('Returned child was not an element. %s', str(child))
        return iq

    def _send(self, iq):
        self.send(iq)
        return iq

    def handler_wrapper(self, handler, iq):
        try:
            d = handler(iq)
        except:
            d = defer.fail()

        d.addCallback(self.success, iq)
        d.addErrback(self.error, iq)
        d.addCallback(self._send)
        iq.handled = True
        return d

    def sendMessage(self, to, frm, typ = 'groupchat', body = None, subject = None, children=[], stz_key = None):
        if stz_key:
            message = self.stz_cache.serialize(stz_key[0], stz_key[2])
            if len(message)>0:
                self.xmlstream.send(message)
                return

        message = domish.Element((NS_CLIENT,'message'))
        message['from'] = frm
        message['to']   = to
        message['type'] = typ
        if subject:            
            if not isinstance(subject, types.StringTypes):
                subject = getCData(subject)
            if subject != '':
                s = message.addElement('subject', None, subject)
            
        if body:
            if not isinstance(body, types.StringTypes):
                body = getCData(body)
            if body != '':
                message.addElement('body', None, body)
        for c in children:
            message.addChild(c)

        if stz_key:
            message = self.stz_cache.start(stz_key[0], message, stz_key[1], stz_key[2]) 
        
        self.xmlstream.send(message)
                                 
    def sendPresence(self, to, frm, typ = None, status = None, show= None, children = None, attrs=None, raw_xml = None):
        """
        Send presence to a xmpp entity
        """
        PRESENCE = u"""<presence%s>%s</presence>"""
        attr_str = u''
        if attrs:
            attrs['to'] = to
            attrs['from'] = frm
            if typ:
                attrs['type'] = typ
            for ak in attrs.keys():
                attr_str = attr_str + u' ' + ak + "='"+ attrs[ak]+"'"
        else:
            attr_str = attr_str + u" to='"+to+"'"        
            attr_str = attr_str + u" from='"+frm+"'"        

            if typ:
                attr_str = attr_str + u" type='"+typ+"'"        
        
        child_str = u""
        if children:
            for c in children:
                if isinstance(c, types.StringTypes):
                    child_str = child_str + c
                else:
                    child_str = child_str + c.toXml()

        if status:
            if isinstance(status, types.StringTypes):
                if status != '':
                    status_str = u"<status>%s</status>" % (status,)
                    child_str = child_str + status_str
            else:
                child_str = child_str + status.toXml()


        if show:
            if isinstance(show, types.StringTypes):
                if show != '':
                    show_str = u"<show>%s</show>" % (show,)
                    child_str = child_str + show_str
            else:
                child_str = child_str + show.toXml()

        if raw_xml:
            child_str = child_str + raw_xml

        self.xmlstream.send(PRESENCE % (attr_str, child_str, ))



    def bcastMessage(self, room_obj, user, body=None, subject = None, typ = 'groupchat', frm = None, children = None, legacy = False):
        """
        Broadcast a message to members in a room.
        """
        if not children:
            children = []
        members = room_obj['roster']
        room = room_obj['name']

        if frm is None:
            frm = jid_escape(room)+'@'+self.jid+'/'+user['nick']

        game_message_type = ''
        # start a stanza broadcast cache
        stz_key = self.stz_cache.getKey()

        for m in members.values():
            if m['role'] == 'none':
                continue
            if m['affiliation'] == 'outcast':
                continue
            # Check for role types?
            if  user['role'] == 'participant' and m['role'] == 'player':
                if room_obj.has_key('ignore_player') and int(room_obj['ignore_player']) == 1:
                    log.msg('Player role ignored')
                else:
                    log.msg('Sender is a participant, do not send to player')
                    continue
            elif user['role'] == 'player' and game_message_type == 'whisper' and m['role'] == 'player':
                log.msg('Sender is a player who is whispering, do not send to other players')
                continue

            self.sendMessage(m['jid'], frm , body=body, subject=subject, typ=typ, children=children, stz_key = (stz_key, 'to', m['jid']))
        self.stz_cache.stop(stz_key)

    def bcastPresence(self, members, room, user, typ = None, px = None, show = None, status = None, attrs = None, private = True, status_code = None):
        # TODO - this needs clean up
        dlist = []

        mucx = domish.Element((NS_MUC, 'x'))

        for m in members.values():
            if m['role'] == 'none' and not status_code:
                continue
            # x = """ """
            x = domish.Element((NS_MUC_USER, 'x'))
            item = x.addElement('item')

            if m['role']=='moderator'\
                    and private:
                item['jid'] = user['jid']
            elif not private:
                item['jid'] = user['jid']

            item['role'] = str(user['role']).lower()

            if user['role'] == 'none':
                typ = 'unavailable'


            if user['affiliation'] != None:
                item['affiliation'] = user['affiliation']

            if status_code:
                s = x.addElement('status')
                s['code'] = str(status_code)
            if user.has_key('xtra'):
                if user['xtra'].has_key('reason'):
                    item.addChild(user['xtra']['reason'])
                if user['xtra'].has_key('actor'):
                    a = item.addElement('actor')
                    a['jid'] = str(user['xtra']['actor'])

            pchildren = [mucx, x]
            if px:
                pchildren = pchildren + px
            if typ != 'unavailable' and typ != 'error' and getattr(self.groupchat,'plugins',None) and self.groupchat.plugins.has_key('extended-presence'):
                ep = self.groupchat.plugins['extended-presence']
                d = ep.member_info(user)
                d.addCallback(self.extendedPresence,
                              m['jid'],
                              room+'@'+self.jid+'/'+user['nick'],
                              typ = typ,
                              children = pchildren,
                              show = show,
                              status = status,
                              attrs = attrs,
                              )
                dlist.append(d)
            else:
                self.sendPresence(m['jid'],
                                  room+'@'+self.jid+'/'+user['nick'],
                                  typ = typ,
                                  children = pchildren,
                                  show = show,
                                  status = status,
                                  attrs = attrs,
                               )
                dlist.append(defer.succeed(True))

        dl = defer.DeferredList(dlist)
        return dl

    def membersPresence(self, members, room, user, private = True):
        dlist = []

        mucx = domish.Element((NS_MUC, 'x'))

        for m in members.values():

            if user['jid'].lower() == m['jid'].lower():
                continue
            if m['role'] == 'none':
                continue
            x = domish.Element((NS_MUC_USER,'x'))
            item = x.addElement('item')

            if user['role']=='moderator'\
               and private:
                item['jid'] = m['jid']
            elif not private:
                item['jid'] = m['jid']
            item['role'] = unicode(m['role']).lower()

            if m['affiliation'] is not None:
                item['affiliation'] = unicode(m['affiliation'])

            mstatus = m.get('status')

            mshow = m.get('show')

            # TODO - need a cache for this, the attribute to change needs to be easier to use.

            # TODO - check if member is not legacy

            pchildren = [mucx, x]

            # TODO - plugins for other things
            if getattr(self.groupchat,'plugins',None) and \
                    self.groupchat.plugins.has_key('extended-presence'):
                ep = self.groupchat.plugins['extended-presence']
                d = ep.member_info(m)
                d.addCallback(self.extendedPresence,
                              user['jid'],
                              room+'@'+self.jid+'/'+m['nick'],
                              children = pchildren,
                              show = mshow,
                              status = mstatus,
                 )
                dlist.append(d)
            else:
                self.sendPresence(user['jid'],
                                  room+'@'+self.jid+'/'+m['nick'],
                                  children = pchildren,
                                  show = mshow,
                                  status = mstatus,
                 )
                dlist.append(defer.succeed(True))

        return defer.DeferredList(dlist)

    def extendedPresence(self, pchildren, to, frm, typ = None, status = None, show= None, children = None, attrs=None, stz_key = None):
        """
        called by the extended presence plugin deffered
        """
        children = children + pchildren

        self.sendPresence(to,
                          frm,
                          typ = typ,
                          children = children,
                          show = show,
                          status = status,
                          attrs = attrs
                          )

class ComponentServiceFromService(Service):

    def __init__(self, groupchat):
        Service.__init__(self, groupchat)

    def get_disco_info(self, room = None, host = None, frm=None):
        info = []

        if not room:
            info.append(disco.Identity('conference', 'text',
                                       'Multi-User Chat Service'))

            info.append(disco.Feature(NS_MUC))
            # TODO - put these in the other services
            info.append(disco.Feature(NS_MUC_USER))
            info.append(disco.Feature(NS_MUC_OWNER))
            info.append(disco.Feature(NS_MUC_ADMIN))
            info.append(disco.Feature(NS_AD_HOC))

            return defer.succeed(info)
        else:
            def trap_not_found(result):
                result.trap(groupchat.RoomNotFound)
                return []

            room = jid_unescape(room)
            d = self.groupchat.getRoom(room, host=host)
            d.addCallback(self._add_room, [], room, frm=frm, host=host)
            d.addErrback(trap_not_found)
            return d

    def _add_room(self, room, result_list, name, frm = None, host = None):
        if room is None:
            return result_list

        if room.has_key('hidden') and room['hidden']:
            # check if user is a member, admin, owner etc
            if not self.groupchat.checkMember(room, frm):
                return result_list


        members = room['roster']
        count = 0
        for mem in members.values():
            if mem['role'] == 'none' and mem['affiliation'] == 'none':
                continue
            count = count + 1
        result_list.append(disco.Identity('conference', 'text',
                                          room['roomname']))
        # add features
        # TODO - this needs to be configurable
        result_list.append(disco.Feature(NS_MUC))
        # TODO - put these in the other services
        result_list.append(disco.Feature(NS_MUC_USER))
        result_list.append(disco.Feature(NS_MUC_OWNER))
        result_list.append(disco.Feature(NS_MUC_ADMIN))
        fields = []
        fields.append({'var': 'FORM_TYPE',
                       'type' :'hidden',
                       'value': NS_MUC_ROOMINFO})
        fields.append({'var': 'muc#roominfo_description',
                       'label' :'Description ',
                       'value': room['description']})

        fields.append({'var': 'muc#roominfo_subject',
                       'label' :'Room Topic',
                       'value': room['subject']})

        fields.append({'var': 'muc#roominfo_occupants',
                       'label' :'Number of Occupants',
                       'value': str(count)})
        x = X(fields=fields)
        if x.hasAttribute('xmlns'):
            del x['xmlns']
        result_list.append(x)
        return result_list


    def get_disco_items(self, room = None, host = None, frm = None, nick = None, node = None):
        def add_items(r):
            # TODO - if a room is not private send room members
            if r and frm and nick:
                if not self.groupchat.checkMember(r, frm):
                    e = domish.Element((None,'error'))
                    e.addElement((NS_XMPP_STANZAS, 'bad-request'), NS_XMPP_STANZAS)
                    e['code'] = '400'
                    e['type'] = 'modify'

                    return [e]
            return []

        def add_rooms(rooms):
            items = []
            for r in rooms:
                room_name = jid_escape(r['name'])
                if type(r['name'])==type(''):
                    des = unicode(r['name'], 'utf8')
                else:
                    des = r['name']

                if type(r['description'])==type(''):
                    description = unicode(r['description'], 'utf-8')
                else:
                    description = r['description']
                # need to check if we are members and can see this room
                
                if frm and self.groupchat.checkMember(r, frm):
                    r['hidden'] = False
                    
                if not r['hidden'] and r['name']:
                    try:
                        rname = jid.internJID(room_name+'@'+self.parent.jabberId).full()
                    except:
                        rname = room_name+'@'+self.parent.jabberId

                    if type(rname) == type(''):
                        rname = unicode(rname, 'utf-8')
                        
                    fields = []
                    
                    fields.append({'var': 'muc#roominfo_description',
                                   'label' :'Description ',
                                   'value': description})
                    if r['subject']:
                        fields.append({'var': 'muc#roominfo_subject',
                                       'label' :'Room Topic',
                                       'value': r['subject']})


                    x = X(fields=fields)
                    ir = disco.Item(rname, name = des, x=x)
                    items.append(ir)

            return items
        
        if room:
            room = jid_unescape(room)
            d = self.groupchat.getRoom(room, frm = frm, host = host)
            d.addCallback(add_items)
            return d
            # return defer.succeed([])
        
        
        d = self.groupchat.getRooms(host = host, frm = frm)
        d.addCallback(add_rooms)
        return d


components.registerAdapter(ComponentServiceFromService,
                           groupchat.IGroupchatService,
                           IService)


class ComponentServiceFromRoomService(Service):
    """
    Handles room occupant actions
    """


    def __init__(self, groupchat, logger = None):
        Service.__init__(self, groupchat, logger)
        self.logger = logger

        self.prs_queue   = {}
        self.msg_queue   = {}
                
    def componentConnected(self, xmlstream):
        self.jid = xmlstream.authenticator.otherHost
        self.xmlstream = xmlstream
        xmlstream.addObserver(PRESENCE, self.onPresence)
        xmlstream.addObserver(GROUP_CHAT, self.onGroupChat, 1)
        xmlstream.addObserver(TCHAT, self.onChat, 2)
        xmlstream.addObserver(MESSAGE_ERROR, self.onMessageError, 3)
        xmlstream.addObserver(IQ, self.onIq, 1)
        self.pending_iqs = {}

        self.groupchat.setUpHistory(self.jid)

        self.startQueue()


    def startQueue(self):
        self.queue = self.groupchat.parent.queue
        self.queue.onPresence = self.onPresence
        self.queue.onGroupChat = self.onGroupChat
        self.queue.start()


    def _doDelay(self, room, frm, chat):
        """Do a delay via our queue
        """
        # FIXME - this is kinda silly, it will need to be redone when we switch protocols and services
        return self.groupchat.parent.queue.doDelay(room, frm, chat)

    def _delStzPending(self, room, frm):
        return self.queue._delStzPending(room, frm)

    def onMessageError(self, msg):
        if msg.hasAttribute('type') and msg['type'] == 'error':
            # remove user from room
            name = jid_unescape(jid.internJID(msg['to']).user)
            frm  = msg['from']
            nick = ''
            if not frm.lower()+name.lower() in self.error_list:
                self._partRoom(name, frm, nick, msg)
                self.error_list.append(frm.lower()+name.lower())

    def forwardIq(self, iq, toitem, frmitem, room, host, nick):
        # if errback then iq would be none
        if not iq:
            return
        riq = domish.Element((NS_CLIENT,'iq'))
        if iq.hasAttribute('type'):
            riq['type'] = iq['type']

        riq.attributes = iq.attributes
        riq.children = iq.children
        riq['from'] = jid_escape(room)+'@'+host+'/'+nick
        riq['to'] = frmitem['jid']
        self.xmlstream.send(riq)
        riq['to'] = toitem['jid']
        self.xmlstream.send(riq)

    def onIq(self, iq):
        if getattr(iq,'handled',False):
            return
        # TODO - should this be in the xpath?
        query = getattr(iq,'query',None)
        if query and query.hasAttribute('xmlns') and (query['xmlns'] == NS_MUC_ADMIN or query['xmlns'] == NS_MUC_OWNER):
            return

        if query and query.uri and (query.uri == NS_MUC_ADMIN or query.uri == NS_MUC_OWNER):
            return

        if query and query.uri and (query.uri == DISCO_NS_INFO or query.uri == DISCO_NS_ITEMS):
            return

        try:
            room = jid_unescape(jid.internJID(iq['to']).user)
            host = jid.internJID(iq['to']).host
            nick = jid.internJID(iq['to']).resource
        except:
            log.msg('Error in jabber id')
            log.err()
            raise groupchat.RoomNotFound
        if not nick:
            return

        if room == host:
            return
        def process_iq(r):
            if not r:
                raise groupchat.RoomNotFound
            if iq['type'] == 'result':
                return

            if r.has_key('privacy') and not r['privacy']:
                raise groupchat.NotAllowed
            # else we pass on the iq to the jid
            fitem = r['roster'].get(iq['from'])
            if not fitem:
                raise groupchat.NotAllowed
            
            for ritem in r['roster'].values():
                if ritem['nick'] == nick:
                    riq = xmlstream.IQ(self.xmlstream, iq['type'])
                    riq.attributes = iq.attributes
                    riq['to'] = ritem['jid']
                    riq['from'] = jid_escape(room)+'@'+host+'/'+nick
                    riq.children = iq.children
                    riq.send().addCallback(self.forwardIq, ritem, fitem, room, host, nick)
                    break
            iq.handled = True
        
        # get room
        
        d = self.groupchat.getRoom(room,host=self.jid)
        d.addCallback(process_iq)
        d.addErrback(self.error, iq)

        return d

    
    def _log(self, room, host, nick, elem):
        """
        Log the room name, host name, nick that sent the element and
        the domish.Element containing the event message.  This
        function uses the configured logger.
        """
        if self.logger:
            self.logger.log(room, host, nick, [elem])
            
    def onPresence(self, prs):
        """
        Add the presence stanza to the queue and grab the room.

        """

        if prs.hasAttribute('type') and prs['type'] == 'error':
            log.msg('\n\npresence errors are bad\n\n')
            # remove user from room
            name = jid_unescape(jid.internJID(prs['to']).user)
            frm  = prs['from']
            nick = jid.internJID(prs['to']).resource
            if not frm.lower()+name.lower() in self.error_list:
                self.error_list.append(frm.lower()+name.lower())

                self._partRoom(name, frm, nick, prs)
            return
        try:
            frmhost  = jid.internJID(prs['from']).host
            room = jid_unescape(jid.internJID(prs['to']).user)
        except:
            error_from_presence(prs, 'jid-malformed', str(prs['from']))
            self.send(prs)
            return

        if frmhost == self.jid:
            log.msg('MUC: This presence is from palaver?')
            return

        frm = prs['from']
        if self._doDelay(room, frm, prs):
            return

        # check if room is active
        if not prs.hasAttribute('type') and \
                jid.internJID(frm).userhost() in self.groupchat.sadmins and \
                self.groupchat.getHistory(room) == None \
                and not self.groupchat.create_rooms:
            # create the room?
            try:
                jabberId, name, host, frm, nick, status, show, legacy = self._getPresenceInfo(prs)
                self._createRoom(prs, name, frm, nick,
                                 status = status,
                                 show = show,
                                 legacy = legacy)
            except:
                pass

        else:
            self._handlePresence(room, prs)


    def _handlePresence(self, room, prs):
        frm = prs['from']
        room = jid_unescape(room)
        self._appendPresence(room+frm, prs)
        d = self.groupchat.getRoom(room, host = self.jid)
        d.addCallback(self._process_presence, room, frm)
        d.addErrback(self.error, prs)



    def _appendPresence(self, key, prs):
        if not self.prs_queue.has_key(key.lower()):
            self.prs_queue[key.lower()] = []
        self.prs_queue[key.lower()].append(prs)

    def _popPresence(self, key, idx = 0):
        p = None
        if self.prs_queue.has_key(key.lower()):
            p = self.prs_queue[key.lower()].pop(idx)
            if len(self.prs_queue[key.lower()]) == 0:
                del self.prs_queue[key.lower()]
        return p

    def _appendMessage(self, msg):
        if not self.msg_queue.has_key(msg['from'].lower()):
            self.msg_queue[msg['from'].lower()] = []
        self.msg_queue[msg['from'].lower()].append(msg)

    def _popMessage(self, frm, idx = -1):
        p = None
        if self.msg_queue.has_key(frm.lower()):
            p = self.msg_queue[frm.lower()].pop(idx)
            if len(self.msg_queue[frm.lower()]) == 0:
                del self.msg_queue[frm.lower()]
        return p


    def _finish_groupchat(self, rtup, chat):
        room_name = jid.internJID(chat['to']).user
        host      = jid.internJID(chat['to']).host
        frm       = chat['from']

        self._delStzPending(jid_unescape(room_name), frm)
        room, user = rtup
        if room is None:
            log.msg('MUC: Room is of value None muc.py (408) ')
            return
        members = room['roster']
        if len(members)==0:
            log.msg('muc.py: _finish_groupchat has no members')
            return

        body    = getattr(chat,'body',None)
        subject = getattr(chat,'subject',None)

        if frm in self.groupchat.sadmins:
            if user:
                nick = user['nick']
            else:
                nick = frm

            user = {'jid': frm,
                    'role': 'moderator',
                    'affiliation': 'owner',
                    'nick': nick,
                    }

        if room.get('logroom'):
            self._log(room_name, host, user['nick'], chat)
        # grab children
        children = []
        # remove the body and subject children
        if body:
            chat.children.pop(chat.children.index(body))
        if subject:
            chat.children.pop(chat.children.index(subject))

        children = chat.children
        self.bcastMessage(room, user, body = body, subject = subject, children = children)

        # FIXME - add this if legacy
        # if subject and body is None:
        #    body = '* '+user['nick'] + ' has changed the subject to ' + getCData(subject)
        #    self.bcastMessage(room, user, body = body, frm = room_name+'@'+self.jid, legacy=True)

    def _joined_room(self, rtup, prs):
        jabberId, room, host, frm, nick, status, show, legacy = self._getPresenceInfo(prs)
        if not rtup:
            self._delStzPending(jid_unescape(room), frm)
            log.msg('Error in joined room. Room is none')
            return
        r, new_user = rtup
        room = jid_escape(room)
        members = r['roster']
        description = None

        self._delStzPending(jid_unescape(room), frm)

        if new_user is None:
            log.msg('error in joined room')
            log.msg(frm)
            log.msg(members)
            raise groupchat.BadRequest

        dlist = []

        # send presence to members
        dbp = self.bcastPresence(members, room, new_user,px=prs.children, show=show, status=status, private=r['private'])

        if dbp:
            dlist.append(dbp)
        else:
            log.msg('Error in bcastPresence')

        # send all member's presence to new member
        dmp = self.membersPresence(members, room, new_user, private=r['private'])
        if dmp:
            dlist.append(dmp)
        else:
            log.msg('Error in membersPresence')

        # send subject
        if r['subject'] != '':
            self.sendMessage(new_user['jid'],
                             room+'@'+self.jid,
                             subject = r['subject'])

        if description:
            self.sendMessage(new_user['jid'],
                             room+'@'+self.jid,
                             body = description)


        if r['join'] != '':
            try:
                body = unicode(new_user['nick']) + ' ' +unicode(r['join'])
                self.bcastMessage(r, new_user, body = body, frm = room+'@'+self.jid, legacy=True)
            except:
                log.err()

        d = defer.DeferredList(dlist)
        ignore = False
        if r.has_key('ignore_player') and int(r['ignore_player'])==1:
            ignore = True
        d.addCallback(lambda _:self.sendHistory(new_user, room, ignore_player=ignore, pres=prs))

        return d

    def sendHistory(self, new_user, room, ignore_player = False, pres = None):
        """ send history to a new user in a room.
         TODO - move this to group chat?
         handle <history since='TS'> and <history maxstanzas='value'>
        """
        maxstanzas = None
        since = None
        if pres is not None:
            history_attr = None
            x = getattr(pres, 'x', None)
            if x is not None:
                history_attr = getattr(x, 'history', None)

            if history_attr is not None:
                maxstanzas = history_attr.getAttribute('maxstanzas', None)
                if history_attr.hasAttribute('since'):
                    since = datetime.datetime.strptime(history_attr['since'],'%Y-%m-%dT%H:%M:%SZ')

        # modification to only get the history list once
        history_els = self.groupchat.getHistory(jid_unescape(room), host=self.jid)
        if history_els:
            # if maxstanzas is set ..  change start index in history list
            startidx = 0
            if maxstanzas is not None:
                if len(history_els) > int(maxstanzas):
                    startidx = len(history_els) - int(maxstanzas)

            # only iterate through the list from startidx
            for h in history_els[startidx::]:
                # check since stamp, if its older ignore it
                if since is not None:
                    if h['stamp'] < since:
                        continue

                # check for size
                x = domish.Element((NS_X_DELAY,'x'))
                # TODO - need a check for configuration on show jids
                x['from'] = room+'@'+self.jid+'/'+h['user']['nick']
                x['stamp'] = h['stamp'].strftime('%Y%m%dT%H:%M:%S')
                children = [x]
                children = children + h['extra']
                if new_user['role']=='player' and not ignore_player:
                    if h['user']['role'] == 'player':
                        self.sendMessage(new_user['jid'],
                                         room+'@'+self.jid+'/'+h['user']['nick'],
                                         body = h['body'],
                                         children = children)
                else:
                    if h['user']['role']!= 'player':
                        self.sendMessage(new_user['jid'],
                                         room+'@'+self.jid+'/'+h['user']['nick'],
                                         body = h['body'],
                                         children = children)

    def _created_room(self, rtup, prs):
        r, new_user = rtup

        room = jid.internJID(prs['to']).user
        frm  = prs['from']

        typ = prs.getAttribute('type')

        description = None
        self._delStzPending(jid_unescape(room), frm)

        if new_user is None:
            raise groupchat.BadRequest

        # send presence to user
        x = domish.Element((NS_MUC_USER,'x'))
        item = x.addElement('item')

        item['jid']  = new_user['jid']
        item['nick'] = new_user['nick']
        item['role'] = new_user['role'].lower()
        item['affiliation'] = new_user['affiliation']

        s = x.addElement('status')
        s['code'] = '201'

        if typ != 'unavailable' and typ != 'error' and getattr(self.groupchat,'plugins',None) and self.groupchat.plugins.has_key('extended-presence'):
            ep = self.groupchat.plugins['extended-presence']
            d = ep.member_info(new_user)
            d.addCallback(self.extendedPresence, new_user['jid'], room+'@'+self.jid+'/'+new_user['nick'],children=[x])
        else:
            self.sendPresence(new_user['jid'],room+'@'+self.jid+'/'+new_user['nick'], children=[x])
        if description:
            self.sendMessage(new_user['jid'],
                             room+'@'+self.jid,
                             body = description)


    def _finish_presence(self, r, prs):
        members = r['roster']
        room = jid.internJID(prs['to']).user

        frm  = prs['from']
        status = getattr(prs, 'status', None)
        show   = getattr(prs, 'show', None)

        self._delStzPending(jid_unescape(room), frm)
        # ignore errors
        if prs.hasAttribute('type') and prs['type']=='error':
            log.msg('MUC: Presence Error?')
            return

        new_user = self.groupchat.getMember(members, frm, host=self.jid)

        if new_user is None:
            raise groupchat.BadRequest

        # send presence to members
        self.bcastPresence(members, room, new_user,show=show, status=status, private=r['private'])


    def _finish_nick(self, r, old_nick, prs):
        members = r['roster']
        room = jid.internJID(prs['to']).user

        frm  = prs['from']
        status = getattr(prs,'status',None)
        show   = getattr(prs,'show',None)

        self._delStzPending(jid_unescape(room), frm)

        # ignore errors
        if prs.hasAttribute('type'):
            if prs['type']=='error':
                log.msg('MUC: Nick Presence Error?')
                return

        new_user = self.groupchat.getMember(members, frm, host=self.jid)

        # send member's presence to new member
        if new_user is None:
            raise groupchat.BadRequest

        new_nick = new_user['nick']

        # send all member's presence to new member
        for m in members.values():
            x = domish.Element((NS_MUC_USER,'x'))
            item = x.addElement('item')

            if m['role']=='moderator'\
                   and r['private']:
                item['jid'] = new_user['jid']
            elif not r['private']:
                item['jid'] = new_user['jid']

            item['nick'] = new_nick
            item['role'] = new_user['role'].lower()
            item['affiliation'] = new_user['affiliation']

            s = x.addElement('status')
            s['code'] = '303'

            self.sendPresence(m['jid'], room+'@'+self.jid+'/'+old_nick, typ='unavailable', children=[x])

        # send presence to members
        self.bcastPresence(members, room, new_user,show=show, status=status, attrs=prs.attributes, private=r['private'])
        if r['rename'] != '':
            body = old_nick + ' ' +r['rename'] + ' ' + new_user['nick']
            old_user = new_user
            old_user['nick'] = old_nick
            self.bcastMessage(r, old_user, body = body, frm = room+'@'+self.jid, legacy = True)


    def _left_room(self, rtup, room, frm, nick, typ='unavailable', prs = None):
        if frm.lower()+room.lower() in self.error_list:
            self.error_list.pop(self.error_list.index(frm.lower()+room.lower()))
        if typ=='error':
            self._delStzPending(room, frm)
            return
        if not rtup:
            log.err('Error in parting the room')
            log.err(room)
            log.err(frm)
            log.err(nick)
            self._delStzPending(room, frm)
            return

        # broadcast left room
        try:
            r, old_user = rtup
        except:
            self._delStzPending(room, frm)
            log.err(rtup)
            raise

        members = r['roster']

        if r.get('logroom') and prs:
            self._log(room, jid.internJID(prs['to']).host, nick, prs)

        if old_user is not None and old_user.has_key('jid'):
            # should we do this?
            x = domish.Element((NS_MUC_USER,'x'))
            # uriCheck(x, NS_MUC_USER)
            item = x.addElement('item')

            if old_user['role']=='moderator'\
                   and r['private']:
                item['jid'] = old_user['jid']
            elif not r['private']:
                item['jid'] = old_user['jid']

            item['role'] = 'none'
            item['affiliation'] = old_user['affiliation']

            self.sendPresence(frm, jid_escape(room)+'@'+self.jid+'/'+old_user['nick'], typ=typ,children=[x])
        else:
            self._delStzPending(room, frm)
            # do nothing for a user not in the room
            return

        if len(members)>0:
            # broad cast presence

            # send message and presence
            old_user['role'] = 'none'

            self.bcastPresence(members, jid_escape(room), old_user, typ = 'unavailable', private=r['private'])

            if r['leave'] != '':
                body = nick + ' '+ r['leave']

                self.bcastMessage(r, old_user, body=body, frm = jid_escape(room)+'@'+self.jid, legacy=True)
        self._delStzPending(room, frm)

    def _getPresenceInfo(self, prs):
        try:
            jabberId = jid.internJID(prs['to'])
            name = jid_unescape(jabberId.user)
            host = jabberId.host
            frm  = prs['from']
            nick = jabberId.resource
        except:
            raise JidMalformed
        if nick is None or nick == '':
            log.msg('Error in jabber id %s ' % (prs['to'], ))
            log.msg(nick)
            raise JidMalformed

        status = getattr(prs,'status',None)
        if status is None:
            status = ''
        else:
            status = getCData(status)
        show   = getattr(prs,'show',None)
        if show is None:
            show = ''
        else:
            show = getCData(show)

        x = getattr(prs,'x',None)

        if x and x.hasAttribute('xmlns') and x['xmlns']==NS_MUC:
            legacy = False
        elif x and x.uri and x.uri==NS_MUC:
            legacy = False
        else:
            legacy = True

        return jabberId, name, host, frm, nick, status, show, legacy

    def _partRoom(self, name, frm, nick, prs):
        self._delStzPending(name, frm)
        d = self.groupchat.partRoom(name, frm, nick, host = self.jid)
        d.addCallback(self._left_room, name, frm, nick, prs = prs)
        d.addErrback(self.error, prs)

    def _process_presence(self, room, name, frm):
        prs = self._popPresence(name+frm)
        if not prs:
            self._delStzPending(jid_unescape(name), frm)
            return

        typ = prs.getAttribute('type')

        jabberId, name, host, frm, nick, status, show, legacy = self._getPresenceInfo(prs)

        if room != None:
            if typ:
                # leave the room
                self._partRoom(name, frm, nick, prs)
                return
            else:
                members = room['roster']
                user = self.groupchat.getMember(members, frm, host = self.jid)

                # This is here for some race conditions and to speed up presence processing
                if self.groupchat.checkBanned(room, frm):
                    raise groupchat.Forbidden
                if room.get('logroom'):
                    self._log(name, host, nick, prs)
                if user:
                    #  broadcast presence to the room
                    if user['nick'] != nick:
                        d = self.groupchat.changeNick(room, user, nick, host=self.jid)
                        d.addCallback(self._finish_nick, user['nick'], prs)
                    else:
                        d = self.groupchat.changeStatus(name,
                                                        user['jid'],
                                                        show   = show,
                                                        status = status,
                                                        legacy = legacy,
                                                        host   = self.jid)
                        d.addCallback(self._finish_presence, prs)

                    return d
                else:
                    # join room
                    d = self.groupchat.joinRoom(name, frm, nick,
                                                status = status,
                                                show = show,
                                                legacy = legacy,
                                                host = self.jid
                                                )
                    d.addCallback(self._joined_room, prs)
                    return d

        else:
            if typ != 'unavailable' and typ != 'error':
                return self._createRoom(prs, name, frm, nick,
                                        status=status,
                                        show=show,
                                        legacy=legacy)
            self._delStzPending(name, frm)

    def _createRoom(self, prs, name, frm, nick, status = None, show = None, legacy = None):
        # create the room

        d = self.groupchat.createRoom(name, frm, nick,
                                      status=status,
                                      show=show,
                                      legacy=legacy,
                                      host=self.jid
                                      )

        if legacy:
            d.addCallback(self._joined_room, prs)
        else:
            d.addCallback(self._created_room, prs)
        return d


    def _on_chat(self, r, chat):
        members = r['roster']
        room = jid_unescape(jid.internJID(chat['to']).user)
        nick = jid.internJID(chat['to']).resource
        frm  = chat['from']
        body = getattr(chat,'body',None)
        # check if allowed
        children = []
        if not nick:
            # not sending a private message to a user
            raise JidMalformed
        to = None
        mfrm = None 
        for m in members.values():
            if m['jid'].lower() == frm.lower():
                mfrm = jid_escape(r['name'])+'@'+self.jid+'/'+m['nick']
            if jid_escape(r['name']) +'@'+ self.jid+'/'+m['nick'] == room+'@'+self.jid+'/'+nick:
                to = m['jid']
        
        if not r['privmsg']:
            raise groupchat.NotAllowed
        
        if to and mfrm:
            for e in chat.elements():
                if e.name != 'body':
                    children.append(e)
            self.sendMessage(to, mfrm , body=body, typ='chat', children=children)

    def onChat(self, chat):
        try:
            room = jid_unescape(jid.internJID(chat['to']).user)
        except:
            log.err()
            return

        # check if we allow private chats
        d = self.groupchat.getRoom(room, host=self.jid)
        d.addCallback(self._on_chat, chat)
        d.addErrback(self.error, chat)
        d.addErrback(self.send)


    def onGroupChat(self, chat):
        frm  = chat.getAttribute('from','')
        try:
            room = jid_unescape(jid.internJID(chat['to']).user)
        except:
            log.err()
            return
        d = None

        if self._doDelay(room, frm, chat):
            return

        subject = getattr(chat, 'subject', None)
        if subject is not None:
            subject = getCData(subject)
            d = self.groupchat.changeSubject(room, frm, subject, host=self.jid)
            d.addCallback(self._finish_groupchat, chat)
            d.addErrback(self.error, chat)
            # should be return here?
            return d

        
        body = getattr(chat, 'body', None)

        extra = []
        # children, this is extra stuff attached to messages
        # look at cleaner way to do this
        # remove the body and subject children
        if body:
            for e in chat.elements():
                if e.name != 'body' and e.name != 'subject':
                    extra.append(e)

        d = self.groupchat.processGroupChat(room, frm, body, extra, host=self.jid)
        d.addCallback(self._finish_groupchat, chat)
        d.addErrback(self.error, chat)
        

components.registerAdapter(ComponentServiceFromRoomService,
                           groupchat.IRoomService,
                           IService)


class ComponentServiceFromAdminService(Service):
    """
    Handles room configuration
    """

    def __init__(self, groupchat):
        Service.__init__(self, groupchat)
        
        self.startQueue()


    def startQueue(self):
        self.queue = self.groupchat.parent.queue
        self.queue.onIqAdmin = self.onAdmin
        self.queue.start()


    def _doDelay(self, room, frm, chat):
        """Do a delay via our queue
        """
        # FIXME - this is kinda silly, it will need to be redone when we switch protocols and services
        return self.groupchat.parent.queue.doDelay(room, frm, chat)

    def _delStzPending(self, room, frm):
        return self.queue._delStzPending(room, frm)

    def componentConnected(self, xmlstream):
        self.jid = xmlstream.authenticator.otherHost
        self.xmlstream = xmlstream
        xmlstream.addObserver(IQ_QUERY, self.onAdmin, 1)
        xmlstream.addObserver(IQ_COMMAND, self.onCommand, 1)
        xmlstream.addObserver(MESSAGE, self.onMessage, -1)

    def onMessage(self, msg):
        if msg.hasAttribute('type') and msg['type'] == 'error':
            # ignore this since this is the admin service            
            return

        x = getattr(msg,'x', None)
        if x:
            try:
                room = jid_unescape(jid.internJID(msg['to']).user)
                frm  = jid.internJID(msg['from']).userhost()
            except:
                log.err()
                return
            # test for invite
            invite = getattr(x,'invite',None)
            if invite:
                if invite.hasAttribute('to'):
                    try:
                        tojid = jid.internJID(invite['to'])
                    except:
                        error_from_message(msg, 'jid-malformed', str(invite['to']))
                        self.send(msg)
                        return

                    if not tojid.user:
                        error_from_message(msg, 'jid-malformed', str(invite['to']))
                        self.send(msg)
                        return
                    if tojid.user == tojid.host:
                        error_from_message(msg, 'jid-malformed', str(invite['to']))
                        self.send(msg)
                        return
                    
                    to = tojid.full()
                    d = self.groupchat.invite(room, to, frm, host=self.jid)              
                    d.addCallback(self.sendInvite, to, frm, invite)
                    d.addErrback(self.error, msg)
                    return
            decline = getattr(x, 'decline', None)
            if decline:
                log.msg(decline.toXml().encode('utf-8','replace'))
                # remove member?
                

    def sendInvite(self, room, to, frm, invite = None):
        message = domish.Element((NS_CLIENT,'message'))
        message['to']   = to
        message['from'] = jid_escape(room['name']) + '@'+ self.jid
        message['type'] = 'normal'
        message.addElement('body',None,'You have been invited to ' + room['name'] + '@'+ self.jid + ' by ' + frm) 
        message.addElement('subject', None, 'Invite')
        x = message.addElement('x')
        # uriCheck(x, NS_MUC_USER)
        x['xmlns'] = NS_MUC_USER
        inv = x.addElement('invite')
        inv['from'] = frm
        # TODO - add password support
        # old school
        ox = message.addElement('x')
        ox['xmlns'] = 'jabber:x:conference'
        ox['jid'] = room['name'] + '@'+ self.jid
        if invite is not None:
            for child in invite.elements():
                c = inv.addChild(child)
                # c.addContent(getCData(child).encode('utf-8','replace'))

        self.xmlstream.send(message)


    def _get_items(self, users, type, user):
        # FIXME - clean up different types for users
        reasons = None
        if type.has_key('affiliation') and type['affiliation'] == 'outcast':
            users, reasons = users
        items = []
        for u in users:
            i = domish.Element((NS_CLIENT,'item'))
            i['affiliation'] = str(type.get('affiliation'))
            i['role']        = str(type.get('role')).lower()
            
            try:
                i['jid'] = u['jid']
            except:
                i['jid'] = u
            if reasons and reasons.has_key(u):
                i.addElement('reason',None, str(reasons[u]))
            items.append(i)

        return items
    
    def getItems(self, iq):
        typ = iq.getAttribute('type')

        room = jid_unescape(jid.internJID(iq['to']).user)
        user = iq['from']
        item = iq.query.item
        type = {}
        d = None
        if item.hasAttribute('affiliation'):
            type['affiliation'] = item['affiliation']
            if item['affiliation'] == 'member':
                d = self.groupchat.getMembers(room, user, host=self.jid)
            if item['affiliation'] == 'admin':
                d = self.groupchat.getAdmins(room, user, host=self.jid)
            if item['affiliation'] == 'outcast':
                d = self.groupchat.getOutcasts(room, user, host=self.jid)
            if item['affiliation'] == 'owner':
                d = self.groupchat.getOwners(room, user, host=self.jid)
            if item['affiliation'] == 'player':
                d = self.groupchat.getPlayers(room, user, host=self.jid)            
        if item.hasAttribute('role'):
            type['role'] = item['role']
            d = self.groupchat.getRoles(room, item['role'], user, host=self.jid)
        
        if not d:
            d = defer.succeed([])    
        
        d.addCallback(self._get_items, type, user)
        
        return d

    def _set_items(self, users, type, user, room):
        items = []
        buser = None
        # TODO - fix this for admin or owner
        #query = domish.Element((NS_MUC_ADMIN,'query'))
        tjid = jid.internJID(user).userhost()
        if users is None:
            return
        for u in users.values():
            ujid = jid.internJID(u['jid']).userhost()
            if ujid.lower() == tjid.lower() or u['nick'] == user:
                buser = u
                break

        if buser:
            # we need to attach other stuff to user?
            buser['xtra'] = type

            if type.has_key('code'):
                status_code = str(type['code'])
            else:
                status_code = None

            self.bcastPresence(users, room, buser, status_code=status_code)
            # remove extra from buser
            del buser['xtra']

        return []

    def setItems(self, iq):
        room = jid_unescape(jid.internJID(iq['to']).user)

        user = iq['from']
        item = iq.query.item
        item_type = {}
        d = None
        # FIXME - need to handle multiple items

        # If we change nick or affiliation then we need to queue up presence till
        # this request finishes. 
        
        if item.hasAttribute('jid'):
            item_type['jid'] = item['jid']
            n = item['jid']
        if item.hasAttribute('nick'):
            item_type['nick'] = item['nick']
            n = item['nick']
        if item.hasAttribute('affiliation'):
            item_type['actor'] = user
            item_type['affiliation'] = item['affiliation']
            
            if item['affiliation'] == 'owner':
                d = self.groupchat.grantOwner(n, room, user, host=self.jid)
            elif item['affiliation'] == 'admin':
                item_type['admin'] = True
                d = self.groupchat.grantAdmin(n, room, user, host=self.jid)
            elif item['affiliation'] == 'member':
                item_type['member'] = True
                d = self.groupchat.grantMembership(n, room, user, host=self.jid)
            elif item['affiliation'] == 'player':
                item_type['player'] = True
                d = self.groupchat.grantPlayer(n, room, user, host=self.jid)                
                
            elif item['affiliation'] == 'outcast':                
                # TODO - support reason
                reason = getattr(item, 'reason', None)
                if reason:
                    item_type['reason'] = reason
                item_type['code'] = '301'
                d = self.groupchat.ban(n, room, user, reason=reason, host=self.jid)
            elif item['affiliation'] == 'none':
                d = self.groupchat.clearAffiliation(n, room, user, host=self.jid)

        if item.hasAttribute('role'):
            item_type['role'] = item['role']
            item_type['actor'] = user
            reason = getattr(item, 'reason', None)
            if reason:
                item_type['reason'] = reason

            if item['role'] == 'none':
                item_type['code'] = '307'
                d = self.groupchat.kick(n, room, user, host=self.jid)
            elif item['role'] != '':
                d = self.groupchat.grantRole(item['role'], n, room, user, host=self.jid)


        if not d:
            d = defer.succeed([])

        d.addCallback(self._set_items, item_type, n, room)
        return d



    def cancelConfig(self, iq):
        return defer.succeed([])

    def onCommand(self, iq):
        """
        Run ad hoc commands specific to palaver.
        """
        if iq['type'] == 'error':
            return
        return self.handler_wrapper(self._onCommand, iq)


    def _onCommand(self, iq):
        
        if iq.command.hasAttribute('node') and iq.command.hasAttribute('action'):
            node   = iq.command['node']
            action = iq.command['action']
            
            if node == 'clearcache' and action == 'execute':
                # reset cache through groupchat
                reset = self.groupchat.resetCache()
                if reset:
                    return defer.succeed(reset)

            if node == 'clearhistory' and action == 'execute':
                d = self.groupchat.getRoom(jid_unescape(jid.internJID(iq['to']).user), iq['from'], host=self.jid)
                # reset cache through groupchat
                d.addCallback(self.groupchat.resetHistory, frm=iq['from'])
                return d
                
                
        raise groupchat.BadRequest
            
        

    def onQuery(self, iq):
        if iq.query.hasAttribute('node') and iq.query['node'] == NS_AD_HOC:
            if iq['type'] == 'get':

                # show the list of commands
                items = []
            
                item = domish.Element((NS_CLIENT,'item'))
                item['jid'] = self.jid
                item['node'] = 'clearcache'
                item['name'] = 'Reset cache'
                
                items.append(item)
                
                item = domish.Element((NS_CLIENT,'item'))
                item['jid'] = self.jid
                item['node'] = 'resethistory'
                item['name'] = 'Reset History'
                
                items.append(item)
                return items


        return []


    def _adminCb(self, iq):
        # reversed attrbiutes because this is a result
        room = jid_unescape(jid.internJID(iq['from']).user)
        frm  = iq.getAttribute('to')
        self._delStzPending(jid_unescape(room), frm)
        return iq

    def onAdmin(self, iq):
        if getattr(iq, 'handled',False):
            return
        # TODO - should this be in the xpath?
        if iq.query.hasAttribute('xmlns') and iq.query['xmlns'] != NS_MUC_ADMIN and iq.query['xmlns'] != NS_MUC_OWNER:
            self.handler_wrapper(self.onQuery, iq)
            return

        if iq.query.uri and iq.query.uri != NS_MUC_ADMIN and iq.query.uri != NS_MUC_OWNER:
            return
        # TODO - move a way to unlock the rooms without an admin service
        typ  = iq.getAttribute('type')

        if typ == 'error':
            return

        room = jid_unescape(jid.internJID(iq['to']).user)
        frm  = iq.getAttribute('from')
        item = getattr(iq.query,'item',None)
        x    = getattr(iq.query,'x',None)

        if self._doDelay(room, frm, iq):
            return

        d = None
        if typ == 'get' and len(iq.query.children)==0:
            # request for configuration of room
            d = self.handler_wrapper(self.getConfig, iq)
        elif item and typ == 'get':
            d = self.handler_wrapper(self.getItems, iq)
        elif item and typ == 'set':
            d = self.handler_wrapper(self.setItems, iq)
        elif x and typ == 'set':
            if x.hasAttribute('type') and x['type'] == 'cancel':
                d = self.handler_wrapper(self.cancelConfig, iq)
            elif x.hasAttribute('type') and x['type'] == 'submit':
                d = self.handler_wrapper(self.setConfig, iq)

        destroy = getattr(iq.query, 'destroy', None)
        if destroy:
            d = self.handler_wrapper(self.destroyRoom, iq)

        if d:
            d.addBoth(self._adminCb)

    def destroyRoom(self, iq):
        room = jid_unescape(jid.internJID(iq['to']).user)
        user = iq['from']

        def ret_destroy(did_it, droom):
            if did_it:
                if not droom:
                    raise groupchat.RoomNotFound

                # send out presence
                destroy_presence = ""
                for mem in droom['roster'].values():
                    if len(destroy_presence)>0:
                        self.xmlstream.send(destroy_presence % (jid.internJID(mem['jid']).full(),
                                                                room+'@'+self.jid+'/'+mem['nick']
                                                                ))
                        continue

                    presence = domish.Element((NS_CLIENT,'presence'))
                    presence['to'] = jid.internJID(mem['jid']).full()
                    presence['type'] = 'unavailable'
                    presence['from'] = room+'@'+self.jid+'/'+mem['nick']
                    x = presence.addElement('x', NS_MUC_USER)
                    i = x.addElement('item')
                    i['affiliation'] = 'none'
                    i['role']        = 'none'
                    if getattr(iq.query,'destroy',None):
                        x.addChild(iq.query.destroy)
                    presence['to'] = '%s'
                    presence['from'] = '%s'
                    destroy_presence = presence.toXml()
                    self.xmlstream.send(destroy_presence % (jid.internJID(mem['jid']).full(), 
                                                            room+'@'+self.jid+'/'+mem['nick']
                                                            ))
            return []
            
        def destroy(r):
            d = self.groupchat.destroyRoom(room, user, host=self.jid)
            d.addCallback(ret_destroy, r)
            return d

        d = self.groupchat.getRoom(room, user, host=self.jid)
        d.addCallback(destroy)
        d.addErrback(self.error, iq)
        return d

    def _get_config(self, room, name, user):
        # TODO - do we need to lock room config?

        # build config

        fields = []
        fields.append({'var': 'FORM_TYPE',
                       'type' :'hidden',
                       'value': NS_MUC_CONFIG})
        fields.append({'var': 'muc#roomconfig_roomname',
                       'type' : 'text-single',
                       'label' : 'Natural language room name.',
                       'value': room['roomname']
                       }
                      )

        fields.append({'var': 'muc#roomconfig_roomdesc',
                       'type' : 'text-multi',
                       'label' : 'Short description of room.',
                       'value': room['description']
                       })

        if room.has_key('enablelogging'):
            if room['enablelogging']:
                elv = '1'
            else:
                elv = '0'
            fields.append({'var': 'muc#roomconfig_enablelogging',
                           'type' : 'boolean',
                           'label' : 'Enable logging?',
                           'value': elv
                           })

        if room['subject_change']:
            elv = '1'
        else:
            elv = '0'
        fields.append({'var': 'muc#roomconfig_subjectchange',
                       'type' : 'boolean',
                       'label' : 'Allow users to change subject?',
                       'value': elv
                       })

        if room.has_key('privacy') and room['privacy']:
            elv = '1'
        else:
            elv = '0'
        fields.append({'var': 'privacy',
                       'type' : 'boolean',
                       'label' : 'Allow users to query others?',
                       'value': elv
                       })

        if room.has_key('invitation') and room['invitation']:
            elv = '1'
        else:
            elv = '0'
        fields.append({'var': 'muc#roomconfig_inviteonly',
                       'type' : 'boolean',
                       'label' : 'An invitation is required to enter?',
                       'value': elv
                       })

        if room.has_key('privmsg') and room['privmsg']:
            elv = '1'
        else:
            elv = '0'
        fields.append({'var': 'privmsg',
                       'type' : 'boolean',
                       'label' : 'Allow users to send private chats?',
                       'value': elv
                       })

        if room.has_key('invites') and room['invites']:
            elv = '1'
        else:
            elv = '0'
        fields.append({'var': 'muc#roomconfig_allowinvites',
                       'type' : 'boolean',
                       'label' : 'Allow users to invite others?',
                       'value': elv
                       })


        if room['private']:
            elv = 'admins'
        else:
            elv = 'anyone'
        fields.append({'var': 'muc#roomconfig_whois',
                       'type' : 'list-single',
                       'label' : 'Afilliations that may discover REAL JIDs of room occupants.',
                       'value': elv,
                       'options' : [{'label': 'Administrators and Moderators only.',
                                     'value' : 'admins'},
                                    {'label': 'Anyone',
                                     'value' : 'anyone'},
                                    ]
                       })
        fields.append({
            'type' : 'fixed',
            'value': 'The following messages are sent to legacy clients.'
        })
        fields.append({'var': 'leave',
                       'type' : 'text-single',
                       'label' : 'Message for user leaving room.',
                       'value': room['leave']
                       })
        fields.append({'var': 'join',
                       'type' : 'text-single',
                       'label': 'Message for user joining room.',
                       'value': room['join']
                       })

        fields.append({'var': 'rename',
                       'type' : 'text-single',
                       'label': 'Message for user changing nick.',
                       'value' : room['rename']
                       })

        if room.has_key('message_size'):
            msg_size = int(room['message_size'])
        else:
            msg_size = 0

        fields.append({'var': 'message_size',
                       'type' : 'text-single',
                       'label': 'Maximum length of messages to chat rooms. 0 for unlimited.',
                       'value' : str(msg_size)
                       })

        fields.append({'var': 'muc#roomconfig_maxusers',
                       'type' : 'list-single',
                       'label': 'Maximum users for this room.',
                       'value' : str(room['maxusers']),
                       'options' : [{'label': '1',
                                     'value' : '1'},
                                    {'label': '10',
                                     'value' : '10'},
                                    {'label': '20',
                                     'value' : '20'},
                                    {'label': '30',
                                     'value' : '30'},
                                    {'label': '40',
                                     'value' : '40'},
                                    {'label': '50',
                                     'value' : '50'},
                                    {'label' : 'unlimited',
                                     'value' : '0'},
                                    ]
                       })

        fields.append({'var': 'history',
                       'type' : 'list-single',
                       'label': 'History backlog length.',
                       'value' : str(room['history']),
                       'options' : [{'label': '1',
                                     'value' : '1'},
                                    {'label': '10',
                                     'value' : '10'},
                                    {'label': '20',
                                     'value' : '20'},
                                    {'label': '30',
                                     'value' : '30'},
                                    {'label': '40',
                                     'value' : '40'},
                                    {'label': '50',
                                     'value' : '50'},
                                    ]
                       })

        if room['hidden']:
            elv = '0'
        else:
            elv = '1'
        fields.append({'var': 'muc#roomconfig_publicroom',
                       'type' : 'boolean',
                       'label' : 'Turn on public searching of room? Make it public.',
                       'value': elv
                       })

        if room['moderated']:
            elv = '1'
        else:
            elv = '0'
        fields.append({'var': 'muc#roomconfig_moderated',
                       'type' : 'boolean',
                       'label' : 'Make room moderated.',
                       'value': elv
                       })

        if room['persistent']:
            elv = '1'
        else:
            elv = '0'
        fields.append({'var': 'muc#roomconfig_persistent',
                       'type' : 'boolean',
                       'label' : 'Make room persistent.',
                       'value': elv
                       })


        elv = str(room.get('logroom', 0))
        fields.append({'var': 'logroom',
                       'type' : 'boolean',
                       'label' : 'Have server log the room.',
                       'value': elv
                       })

        elv = str(room.get('ignore_player', 0))
        fields.append({'var': 'ignore_player',
                       'type' : 'boolean',
                       'label' : 'Ignore player checks for games.',
                       'value': elv
                       })

        x = X(typ='form',
              title='Configuration for "'+name+'" Room',
              instructions='Complete this form to configure this chat room.',
              fields=fields)

        return [x]

    def getConfig(self, iq):
        room = jid_unescape(jid.internJID(iq['to']).user)
        d = self.groupchat.getRoomConfig(room, iq['from'], host=self.jid)
        d.addCallback(self._get_config, room, iq['from'])
        return d


    def _set_config(self, room, x, name, user):
        if room is None:
            raise groupchat.RoomNotFound

        # build config

        kwargs = {}
        kwargs['host'] = self.jid
        if room['locked']:
            kwargs['locked'] = False

        for f in x.elements():
            if f.name == 'field' and f.hasAttribute('var'):
                if f['var'] == 'muc#roomconfig_subject':
                    kwargs['subject'] = getCData(f.value)
                elif f['var'] == 'muc#roomconfig_subjectchange':
                    if str(f.value)=='1':
                        kwargs['subject_change'] = True
                    else:
                        kwargs['subject_change'] = False
                elif f['var'] == 'muc#roomconfig_whois':
                    if str(f.value)=='admins':
                        kwargs['private'] = True
                    else:
                        kwargs['private'] = False
                elif f['var'] == 'muc#roomconfig_roomdesc':
                    kwargs['description'] = unicode(f.value)
                elif f['var'] == 'muc#roomconfig_roomname':
                    kwargs['roomname'] = unicode(f.value)
                elif f['var'] == 'muc#roomconfig_maxusers':
                    kwargs['maxusers'] = str(f.value)
                elif f['var'] == 'muc#roomconfig_persistent':
                    if str(f.value)=='0':
                        p = False
                    else:
                        p = True
                    kwargs['persistent'] = p
                elif f['var'] == 'privacy':
                    if str(f.value)=='0':
                        p = False
                    else:
                        p = True
                    kwargs['privacy'] = p                    
                elif f['var'] == 'muc#roomconfig_inviteonly':
                    if str(f.value)=='0':
                        p = False
                    else:
                        p = True
                    kwargs['invitation'] = p
                elif f['var'] == 'muc#roomconfig_allowinvites':
                    if str(f.value)=='0':
                        p = False
                    else:
                        p = True
                    kwargs['invites'] = p

                elif f['var'] == 'muc#roomconfig_moderated':
                    if str(f.value)=='0':
                        p = False
                    else:
                        p = True
                    kwargs['moderated'] = p
                elif f['var'] == 'muc#roomconfig_publicroom':
                    if str(f.value)=='0':
                        p = True
                    else:
                        p = False
                    kwargs['hidden'] = p
                elif f['var'] == 'privmsg':
                    if str(f.value)=='0':
                        p = False
                    else:
                        p = True
                    kwargs['privmsg'] = p
                else:
                    kwargs[str(f['var'])] = unicode(f.value)
        if len(kwargs)>0:
            d = self.groupchat.updateRoom(name, user, **kwargs)
            d.addCallback(lambda _: [])
            return d
        return []

    def setConfig(self, iq):
        room = jid_unescape(jid.internJID(iq['to']).user)
        user = iq['from']
        x    = getattr(iq.query,'x',None)
        d = self.groupchat.getRoomConfig(room, user, host=self.jid)
        d.addCallback(self._set_config, x, room, user)

        return d

components.registerAdapter(ComponentServiceFromAdminService,
                           groupchat.IAdminService,
                           IService)


