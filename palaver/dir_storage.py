# Copyright (c) 2005 - 2007  Christopher Zorn, OGG, LLC 
# See LICENSE.txt for details
import copy

from twisted.internet import defer, reactor
from twisted.python import log
from twisted.words.protocols.jabber import jid
from zope.interface import implements

from twisted.persisted import dirdbm

def StorageError(Error):
    pass

# maybe move groupchat
import groupchat
import storage


class Storage:

    implements(storage.IStorage)
    sadmins = []

    def __init__(self, spool):
        self.spool_dir = spool
        self.rooms = spool + '/rooms.xml'
        self.spool = dirdbm.Shelf(spool)
        if not self.spool.has_key('rooms'):
            self.spool['rooms'] = {}
        
    

    def _room_exists(self, room):
        if self.spool['rooms'].has_key(room):
            return True
        return False

    def createRoom(self, room, owner, **kwargs):
        #
        if self._room_exists(room):
            raise groupchat.RoomExists

        temp = self.spool['rooms']

        temp[room] = {}
        temp[room]['name']           = room
        temp[room]['roomname']       = room
        temp[room]['subject']        = ''
        temp[room]['subject_change'] = True
        temp[room]['persistent']     = False
        temp[room]['moderated']      = False
        temp[room]['private']        = True
        temp[room]['history']        = 10
        temp[room]['game']           = False
        temp[room]['inivtation']     = False
        temp[room]['invites']        = True
        temp[room]['hidden']         = False
        temp[room]['privacy']        = False
        temp[room]['locked']         = True
        temp[room]['subjectlocked']  = False
        temp[room]['description']    = room
        temp[room]['leave']          = ''
        temp[room]['join']           = ''
        temp[room]['rename']         = ''
        temp[room]['maxusers']       = 30
        temp[room]['privmsg']        = True
        temp[room]['change_nick']    = True
        temp[room]['query_occupants']= False
    

        # is there a better way to do this?
        for arg in kwargs:
            if arg == 'legacy':
                if kwargs[arg]:
                    temp[room]['locked'] = False
            else:
                temp[room][arg] = kwargs[arg]
            
        temp[room]['owner']   = {}
        temp[room]['member']  = {}
        temp[room]['admin']   = {}
        temp[room]['outcast'] = {}
        temp[room]['roster']  = {}
        temp[room]['player']  = {}
        temp[room]['reason']  = {}
        jowner = jid.JID(owner).userhost()
        temp[room]['owner'][jowner] = jowner
        self.spool['rooms'] = temp

        return defer.succeed(room)

    
    def setRole(self, room, user, role, host=None):    
        try:
            return defer.succeed(self._set_role(room, user, role))
        except:
            return defer.fail()
        
    def _set_role(self, room, user, role, host=None):
        rooms = self.spool['rooms']
        if rooms.has_key(room):
            for k, u in rooms[room]['roster'].iteritems():
                if u['jid'].lower() == user.lower():
                    u['role'] = role
                    if role == 'none':
                        del rooms[room]['roster'][k]
                    else:
                        rooms[room]['roster'][k.lower()] = u
                
            self.spool['rooms'] = rooms    
            return rooms
        else:
            raise groupchat.RoomNotFound
        
    
    
    

    def getRole(self, room, user, host=None):
        role = None
        for u in self.spool['rooms'][room]['roster']:
            if u['jid'].lower() == user.lower():
                role = u['role']
        return defer.succeed(role)


    def setAffiliation(self, room, user, affiliation, reason=None, host=None):
        try:
            return defer.succeed(self._set_affiliation(room, user, affiliation, reason=reason))
        except:
            return defer.fail()
        
    def _set_affiliation(self, room, user, affiliation, reason=None, host=None):        
        rooms = self.spool['rooms']
        if rooms.has_key(room):
            rooms = self._clear_affiliations(room,user)
            # rooms = self._set_role(room, user, 'none')
            # print rooms[room]['roster']
            if affiliation == 'owner':
                if user not in rooms[room]['owner']:
                    rooms[room]['owner'][user] = user
            if affiliation == 'admin':
                if user not in rooms[room]['admin']:
                    rooms[room]['admin'][user] = user
            if affiliation == 'member':
                if user not in rooms[room]['member']:
                    rooms[room]['member'][user] = user
            if affiliation == 'outcast':
                if user not in rooms[room]['outcast']:
                    rooms[room]['outcast'][user] = user
                    if reason:
                        rooms[room]['reason'][user] = str(reason)

            if affiliation == 'player':
                if user not in rooms[room]['player']:
                    rooms[room]['player'][user] = user

            for u in rooms[room]['roster'].values():
                if u['jid'].lower() == user.lower():
                    u['affiliation'] = affiliation
                    if affiliation == 'outcast':
                        
                        del rooms[room]['roster'][u['jid'].lower()]
                    else:
                        rooms[room]['roster'][u['jid'].lower()] = u
                
            self.spool['rooms'] = rooms
            return rooms
        else:
            raise groupchat.RoomNotFound
        

    def setOutcast(self, room, user, reason=None, host = None):
        return self.setAffiliation(room, user, 'outcast', reason = reason, host = host)


    def getAffiliation(self, room, user, host=None):
        affiliation = self._getAffiliation(room, user, host)
        return defer.succeed(affiliation)

    def _getAffiliation(self, room, user, host = None):
        affiliation = 'none'
        if self._room_exists(room):                
            for u in self.spool['rooms'][room]['roster'].values():
                if u['jid'].lower() == user.lower():
                    affiliation = u['affiliation']
                    break
        return affiliation
                
    def setNewRole(self, room, user, host = None):
        u = self._setNewRole(room, user, host)
        return defer.succeed(u['role'])
    
    def _setNewRole(self, room, user, host = None):
        rooms = self.spool['rooms']
        u = None
        ju = jid.internJID(user).userhost()
        # should this be done in storage?
        if rooms.has_key(room):
            i = 0
            for r in rooms[room]['roster'].values():
                if r['jid'].lower() == user.lower():
                    u = r
                    del rooms[room]['roster'][r['jid'].lower()]
                    break
                i += 1
            u['role'] = 'participant'
            for o in rooms[room]['outcast'].keys():
                if o.lower() == ju.lower():
                    u['affiliation'] = 'outcast'
                    if rooms[room]['reason'].has_key(user):
                        u['reason'] = rooms[room]['reason'][user]
                            
            for o in rooms[room]['member'].keys():
                if o.lower() == ju.lower():
                    u['role'] = 'participant'
                    u['affiliation'] = 'member'
            for o in rooms[room]['player'].keys():
                if o.lower() == ju.lower():
                    u['role'] = 'player'
                    u['affiliation'] = 'player'
            for o in rooms[room]['admin'].keys() + self.sadmins:
                if o.lower() == ju.lower():
                    u['role'] = 'moderator'
                    u['affiliation'] = 'admin'
            for o in rooms[room]['owner'].keys():
                if o.lower() == ju.lower():
                    u['affiliation'] = 'owner'
                    u['role'] = 'moderator'
                    
            rooms[room]['roster'][user.lower()] = u
        self.spool['rooms'] = rooms    
        return u['role']


    def joinRoom(self, room, user, nick, status = None, show=None, legacy=True, host=None):
        rooms = self.spool['rooms']
        new_user = None
        # find user

        if rooms.has_key(room):
            for u in rooms[room]['roster'].values():
                if u['jid'].lower() == user.lower():
                    new_user = u
                    #del rooms[room]['roster'][rooms[room]['roster'].index(u)]
                
        if new_user:
            log.msg('Already in roster?')
         
        else:
            u = {}
            ju = jid.JID(user).userhost()
            u['jid']  = user
            if rooms[room]['moderated']:
                u['role'] = 'visitor'
            else:
                u['role'] = 'participant'

            u['affiliation'] = self._getAffiliation(room, user, host)

            u['nick'] = nick
            u['legacy'] = legacy
            u['show'] = show
            u['status'] = status
            
            rooms[room]['roster'][user.lower()] = u
            self.spool['rooms'] = rooms    
            u['role'] = self._setNewRole(room, user, host)

            return defer.succeed(True)        
        
        
        return defer.succeed(self._get_room(room))
        

    def partRoom(self, room, user, nick, host=None):
        # check for room types, grab role and affiliation
        rooms = self.spool['rooms']
        old_u = None
        if rooms.has_key(room):
            old_u = rooms[room]['roster'].get(user.lower())
            if not old_u:
                for u in rooms[room]['roster'].values():
                    if u['jid'].lower() == user.lower() and u['nick'].lower()==nick.lower():
                        old_u = u
            if old_u:
                del rooms[room]['roster'][old_u['jid'].lower()]            
            self.spool['rooms'] = rooms
            return defer.succeed(old_u)
        else:
            return defer.fail(groupchat.RoomNotFound)
    

    def _get_room_members(self,  room, host=None):
        members = []
        
        if self.spool['rooms'].has_key(room):
            #args    = self.spool['rooms'][room]
            members = self.spool['rooms'][room]['roster']

        return members
        
    def getRoomMembers(self, room, host=None, frm=None):
        return defer.succeed(self._get_room_members(room))
    

    def deleteRoom(self, room, owner = None, check_persistent = False, host=None):
        if check_persistent and self._room_exists(room):
            p = self.spool['rooms'][room]['persistent']            
            if p:
                return defer.succeed(False)
        
        temp = self.spool['rooms']
        if temp.has_key(room):
            del temp[room]

        self.spool['rooms'] = temp
        
        if self.spool['rooms'].has_key(room):
            return defer.succeed(False)
        return defer.succeed(True)


    def setOwner(self, room, user, host = None):
        rooms = self.spool['rooms']
        if rooms.has_key(room):
            rooms = self._clear_affiliations(room,user)
            rooms = self._set_role(room, user, 'moderator')
            rooms = self._set_affiliation(room, user, 'owner')
            if user not in rooms[room]['owner']:
                rooms[room]['owner'][user] = user
                
            self.spool['rooms'] = rooms    
            return defer.succeed(rooms[room])
        else:
            return defer.fail(groupchat.RoomNotFound)

    def setPlayer(self, room, user, host = None):
        rooms = self.spool['rooms']

        if rooms.has_key(room):
            rooms = self._clear_affiliations(room,user)
            if not rooms[room].has_key('player'):
                rooms[room]['player'] = []
            rooms = self._set_role(room, user, 'player')
            rooms = self._set_affiliation(room, user, 'player')
            if user not in rooms[room]['player']:
                rooms[room]['player'][user] = user
                
            self.spool['rooms'] = rooms    
            return defer.succeed(rooms[room])
        else:
            return defer.fail(groupchat.RoomNotFound)


    def setAdmin(self, room, user, host = None):
        rooms = self.spool['rooms']
        if rooms.has_key(room):
            rooms = self._clear_affiliations(room,user)
            rooms = self._set_role(room, user, 'moderator')
            rooms = self._set_affiliation(room, user, 'owner')
            if user not in rooms[room]['admin']:
                rooms[room]['admin'] = user
                
            self.spool['rooms'] = rooms
            
            return defer.succeed(rooms[room])
        else:
            return defer.fail(groupchat.RoomNotFound)


    def _clear_affiliations(self, room, user, host = None):
        rooms = self.spool['rooms']
        if rooms.has_key(room):
            if user in rooms[room]['member']:
                del rooms[room]['member'][user]
            if user in rooms[room]['admin']:
                del rooms[room]['admin'][user]
                
            if user in rooms[room]['outcast']:
                del rooms[room]['outcast'][user]
            if user in rooms[room]['owner']:
                del rooms[room]['owner'][user]
            
            self.spool['rooms'] = rooms    
            return rooms
        else:
            raise groupchat.RoomNotFound

    def setMember(self, room, user, host = None):
        rooms = self.spool['rooms']
        
        if rooms.has_key(room):
            # TODO - maybe switch setMember, setAdmin, etc to setAffiliation?
            rooms = self._clear_affiliations(room,user)
            rooms = self._set_role(room, user, 'participant')
            rooms = self._set_affiliation(room, user, 'member')
            if user not in rooms[room]['member']:
                rooms[room]['member'][user] = user
            
            self.spool['rooms'] = rooms    
            return defer.succeed(rooms[room])
        
        else:
            return defer.fail(groupchat.RoomNotFound)

    def changeNick(self, room, user, nick, host = None):
        rooms = self.spool['rooms']
        if rooms.has_key(room):
            for u in rooms[room]['roster'].values():
                if u['jid'].lower() == user.lower():
                    u['nick'] = nick
                    rooms[room]['roster'][u['jid']] = u
                
            self.spool['rooms'] = rooms    
            return defer.succeed(rooms[room])
        else:
            return defer.fail(groupchat.RoomNotFound)

    def getNicks(self, room, host = None):
        nicks = []
        if self.spool['rooms'].has_key(room):
            for u in self.spool['rooms'][room]['roster'].values():
                nicks.append(u['nick'])
            
        return defer.succeed(nicks)
    
    
    def updateRoom(self, room, **kwargs):
        rooms = self.spool['rooms']
        
        if rooms.has_key(room):
            # is there a better way to do this?
            try:
                for arg in kwargs:
                    rooms[room][arg] = kwargs[arg]
                self.spool['rooms'] = rooms
                return defer.succeed(rooms[room])
            except:
                log.err()
                return defer.fail(groupchat.RoomNotFound)
        else:
            return defer.fail(groupchat.RoomNotFound)
        
    def _get_room(self, room, host = None):
        if self.spool['rooms'].has_key(room):
            return self.spool['rooms'][room]
            
        else:
            return None
        
    def getRoom(self, room, host = None, frm = None):
        #return self.handler(self._get_room, room)
        return defer.succeed(self._get_room(room))


    def _get_rooms(self, host = None, frm=None):
        # backwards for sql backends?
        ret = []
        for r in self.spool['rooms']:
            ret.append(self.spool['rooms'][r])
        return ret

    def getRooms(self, host = None, frm = None):
        return defer.succeed(self._get_rooms(host=host, frm=frm))

    def changeStatus(self, room, user, show = None, status = None, legacy=True, host = None):
        rooms = self.spool['rooms']
        if rooms.has_key(room):
            for u in rooms[room]['roster'].values():
                if u['jid'].lower() == user.lower():
                    if status:
                        u['status'] = status
                    else:
                        u['status'] = ''
                    if show:
                        u['show'] = show
                    else:
                        u['show'] = ''
                    u['legacy'] = legacy
                    rooms[room]['roster'][u['jid']] = u
                
            self.spool['rooms'] = rooms    
            return defer.succeed(rooms[room])
        else:
            return defer.fail(groupchat.RoomNotFound)

