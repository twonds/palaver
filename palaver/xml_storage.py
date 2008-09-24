# Copyright (c) 2005 Christopher Zorn, OGG, LLC 
# See LICENSE.txt for details
import copy

from twisted.internet import defer, reactor
from twisted.words.protocols.jabber import jid
from zope.interface import implements


def StorageError(Error):
    pass

# maybe move groupchat
import groupchat
import storage

class Storage:

    implements(storage.IStorage)

    def __init__(self):
        self.spool = {}
        if not self.spool.has_key('rooms'):
            self.spool['rooms'] = {}
        
    def handler(self, cb, *args, **kwargs):
        # this needs work, should be do threads?
        d = defer.Deferred()
        reactor.callLater(0, self.handle, d, cb, *args, **kwargs) 
        return d
    
    def handle(self, d, cb, *args, **kwargs):
        try:
            out = cb(*args, **kwargs)
            d.callback(out)
        except:
            d.errback()

    

    def _room_exists(self, room):
        if self.spool['rooms'].has_key(room):
            return True
        return False

    def _create_room(self, room, owner, **kwargs):
        #
        if self._room_exists(room):
            raise groupchat.RoomExists

        temp = self.spool['rooms']

        temp[room] = {}
        temp[room]['name']          = room
        temp[room]['roomname']      = room
        temp[room]['subject']       = ''
        temp[room]['subject_change']= True
        temp[room]['persistent']    = False
        temp[room]['moderated']     = False
        temp[room]['private']       = True
        temp[room]['history']       = 10
        temp[room]['game']          = False
        temp[room]['inivtation']    = False
        temp[room]['invites']       = False
        temp[room]['hidden']        = False
        temp[room]['locked']        = True
        temp[room]['subjectlocked'] = False
        temp[room]['description']   = room
        temp[room]['leave']         = ''
        temp[room]['join']          = ''
        temp[room]['rename']        = ''
        temp[room]['maxusers']      = 30
        temp[room]['privmsg']       = True
        temp[room]['change_nick']   = True
    

        # is there a better way to do this?
        for arg in kwargs:
            temp[room][arg] = kwargs[arg]
            
        temp[room]['owner']   = []
        temp[room]['member']  = []
        temp[room]['admin']   = []
        temp[room]['outcast'] = []
        temp[room]['roster']  = []
        jowner = jid.JID(owner).userhost()
        temp[room]['owner'].append(jowner)
        self.spool['rooms'] = temp

        return room

    def createRoom(self, room, owner, **kwargs):
        # this is a bogus defered right now
        return self.handler(self._create_room, room, owner, **kwargs)

    
    def _set_role(self,  room, user, role):
        
        rooms = self.spool['rooms']
        if rooms.has_key(room):
            for u in rooms[room]['roster']:
                if u['jid'] == user:
                    u['role'] = role
                    if role == 'none':
                        del rooms[room]['roster'][rooms[room]['roster'].index(u)]
                    else:
                        rooms[room]['roster'][rooms[room]['roster'].index(u)] = u
                
            self.spool['rooms'] = rooms    
            return rooms
        else:
            raise groupchat.RoomNotFound
        
    
    def setRole(self, room, user, role):
        return self.handler(self._set_role, room, user, role)

    

    def _get_role(self, room, user):
        role = None
        for u in self.spool['rooms'][room]['roster']:
            if u['jid'] == user:
                role = u['role']
        return role

    
    def getRole(self, room, user):
        return self.handler(self._get_role, room, user)


    def _set_affiliation(self,  room, user, affiliation):
        
        rooms = self.spool['rooms']
        if rooms.has_key(room):
            rooms = self._clear_affiliations(room,user)
            rooms = self._set_role(room, user, 'none')
            if affiliation == 'owner':
                if user not in rooms[room]['owner']:
                    rooms[room]['member'].append(user)
            if affiliation == 'admin':
                if user not in rooms[room]['admin']:
                    rooms[room]['admin'].append(user)
            if affiliation == 'member':
                if user not in rooms[room]['member']:
                    rooms[room]['member'].append(user)
            if affiliation == 'outcast':
                if user not in rooms[room]['outcast']:
                    rooms[room]['outcast'].append(user)

            for u in rooms[room]['roster']:
                if u['jid'] == user:
                    u['affiliation'] = affiliation
                    if affiliation == 'outcast':
                        
                        del rooms[room]['roster'][rooms[room]['roster'].index(u)]
                    else:
                        rooms[room]['roster'][rooms[room]['roster'].index(u)] = u
                
            self.spool['rooms'] = rooms    
            return rooms
        else:
            raise groupchat.RoomNotFound
        
    
    def setAffiliation(self, room, user, affiliation):
        return self.handler(self._set_affiliation, room, user, affiliation)

    

    def _get_affiliation(self, room, user):
        affiliation = None
        for u in self.spool['rooms'][room]['roster']:
            if u['jid'] == user:
                affiliation = u['affiliation']
        return affiliation

    
    def getAffiliation(self, room, user):
        return self.handler(self._get_affiliation, room, user)

    def _join_room(self,  room, user, nick, status=None, show=None, legacy=True):
        rooms = self.spool['rooms']
        new_user = None
        # find user

        if rooms.has_key(room):
            for u in rooms[room]['roster']:
                if u['jid'] == user:
                    new_user = u
                    #del rooms[room]['roster'][rooms[room]['roster'].index(u)]
                
        if new_user:
            print 'Already in roster?'
         
        else:
            u = {}
            ju = jid.JID(user).userhost()
            u['jid']  = user
            if rooms[room]['moderated']:
                u['role'] = 'visitor'
            else:
                u['role'] = 'participant'
            u['affiliation'] = 'none'
            
            u['nick'] = nick
            u['legacy'] = legacy
            u['show'] = show
            u['status'] = status
                            
            # should this be done in storage?
            if rooms.has_key(room):
                for o in rooms[room]['outcast']:
                    print "Is %s an outcast?" % ju
                    if o == ju:
                        u['affiliation'] = 'outcast'
                        #raise groupchat.NotAllowed

                for o in rooms[room]['member']:
                    print "Is %s a member?" % ju
                    if o == ju:
                        u['role'] = 'participant'
                        u['affiliation'] = 'member'
                for o in rooms[room]['admin']:
                    print "Is %s an admin?" % ju
                    if o == ju:
                        u['role'] = 'moderator'
                        u['affiliation'] = 'admin'
                for o in rooms[room]['owner']:
                    print "Is %s an owner?" % ju
                    print o

                    if o == ju:
                        u['affiliation'] = 'owner'
                        u['role'] = 'moderator'
                    
                rooms[room]['roster'].append(u)
        
        self.spool['rooms'] = rooms
        
        return self._get_room(room)
        

    def joinRoom(self, room, user, nick, status = None, show=None, legacy=True):
        return self.handler(self._join_room, room, user, nick,
                            status=status,
                            show=show,
                            legacy=legacy)


    def _part_room(self,  room, user, nick):
        # check for room types, grab role and affiliation
        rooms = self.spool['rooms']
        old_u = None
        if rooms.has_key(room):
            for u in rooms[room]['roster']:
                if u['jid'] == user and u['nick']==nick:
                    old_u = u
                    del rooms[room]['roster'][rooms[room]['roster'].index(u)]

            self.spool['rooms'] = rooms    
            return rooms[room], old_u
        else:
            raise groupchat.RoomNotFound
    

    def partRoom(self, room, user, nick):
        return self.handler(self._part_room, room, user, nick)



    def _get_room_members(self,  room):
        members = []
        
        if self.spool['rooms'].has_key(room):
            #args    = self.spool['rooms'][room]
            members = self.spool['rooms'][room]['roster']

        return members
        
    def getRoomMembers(self, room):
        return self.handler(self._get_room_members, room)
    

    def _delete_room(self, room, owner = None, check_persistent = False):
        if check_persistent:
            p = self.spool['rooms'][room]['persistent']
            if p:
                return p
        temp = self.spool['rooms']

        del temp[room]

        self.spool['rooms'] = temp
        
        if self.spool['rooms'].has_key(room):
            return False
        return False


    def deleteRoom(self, room, owner = None, check_persistent = False):
        return self.handler(self._delete_room, room, owner = owner, check_persistent = check_persistent)


    def _set_owner(self, room, user):
        rooms = self.spool['rooms']
        if rooms.has_key(room):
            rooms = self._clear_affiliations(room,user)
            rooms = self._set_role(room, user, 'moderator')
            rooms = self._set_affiliation(room, user, 'owner')
            if user not in rooms[room]['owner']:
                rooms[room]['owner'].append(user)
                
            self.spool['rooms'] = rooms    
            return user
        else:
            raise groupchat.RoomNotFound

    def setOwner(self, room, user):
        return self.handler(self._set_owner, room, user)


    def _set_admin(self, room, user):
        rooms = self.spool['rooms']
        if rooms.has_key(room):
            rooms = self._clear_affiliations(room,user)
            rooms = self._set_role(room, user, 'moderator')
            rooms = self._set_affiliation(room, user, 'owner')
            if user not in rooms[room]['admin']:
                rooms[room]['admin'].append(user)
                
            self.spool['rooms'] = rooms
            
            return user
        else:
            raise groupchat.RoomNotFound

    def setAdmin(self, room, user):
        return self.handler(self._set_admin, room, user)

    def _clear_affiliations(self, room, user):
        rooms = self.spool['rooms']
        if rooms.has_key(room):
            if user in rooms[room]['member']:
                del rooms[room]['member'][rooms[room]['member'].index(user)]
            if user in rooms[room]['admin']:
                del rooms[room]['admin'][rooms[room]['admin'].index(user)]
                
            if user in rooms[room]['outcast']:
                del rooms[room]['outcast'][rooms[room]['outcast'].index(user)]
            if user in rooms[room]['owner']:
                del rooms[room]['owner'][rooms[room]['owner'].index(user)]
            
            self.spool['rooms'] = rooms    
            return rooms
        else:
            raise groupchat.RoomNotFound

    def _set_member(self, room, user):
        rooms = self.spool['rooms']
        
        if rooms.has_key(room):
            # TODO - maybe switch setMember, setAdmin, etc to setAffiliation?
            rooms = self._clear_affiliations(room,user)
            rooms = self._set_role(room, user, 'participant')
            rooms = self._set_affiliation(room, user, 'member')
            if user not in rooms[room]['member']:
                rooms[room]['member'].append(user)
            
            self.spool['rooms'] = rooms    

        else:
            raise groupchat.RoomNotFound

    def setMember(self, room, user):
        return self.handler(self._set_member, room, user)

    def _change_nick(self, room, user, nick):
        rooms = self.spool['rooms']
        if rooms.has_key(room):
            for u in rooms[room]['roster']:
                if u['jid'] == user:
                    u['nick'] = nick
                    rooms[room]['roster'][rooms[room]['roster'].index(u)] = u
                
            self.spool['rooms'] = rooms    
            return nick
        else:
            raise groupchat.RoomNotFound

    def changeNick(self, room, user, nick):
        return self.handler(self._change_nick, room, user, nick)

    def _get_nicks(self, room):
        nicks = []
        if self.spool['rooms'].has_key(room):
            for u in self.spool['rooms'][room]['roster']:
                nicks.append(u['nick'])
            
        return nicks
    
    def getNicks(self, room):
        return self.handler(self._get_nicks, room)
    
    def _update_room(self, room, **kwargs):
        rooms = self.spool['rooms']
        if self.spool['rooms'].has_key(room):
                        

            # is there a better way to do this?
            for arg in kwargs:
                rooms[room][arg] = kwargs[arg]

            self.spool['rooms'] = rooms
            return self.spool['rooms'][room]
        else:
            raise groupchat.RoomNotFound
        
    def updateRoom(self, room, **kwargs):
        return self.handler(self._update_room, room, **kwargs)


    def _get_room(self, room):
        # backwards for sql backends?
        #ret = []

        if self.spool['rooms'].has_key(room):
            return self.spool['rooms'][room]
            
        else:
            return None
        
    def getRoom(self, room):
        return self.handler(self._get_room, room)


    def _get_rooms(self):
        # backwards for sql backends?
        ret = []
        for r in self.spool['rooms']:
            
            ret.append(self.spool['rooms'][r])
        return ret

    def getRooms(self):
        return self.handler(self._get_rooms)

    def _change_status(self, room, user, show, status, legacy):
        rooms = self.spool['rooms']
        if rooms.has_key(room):
            for u in rooms[room]['roster']:
                if u['jid'] == user:
                    if status:
                        u['status'] = status
                    else:
                        u['status'] = ''
                    if show:
                        u['show'] = show
                    else:
                        u['show'] = ''
                    u['legacy'] = legacy
                    rooms[room]['roster'][rooms[room]['roster'].index(u)] = u
                
            self.spool['rooms'] = rooms    
            return rooms[room]['roster']
        else:
            raise groupchat.RoomNotFound

    def changeStatus(self, room, user, show = None, status = None, legacy=True):
        return self.handler(self._change_status, room, user, show, status, legacy)
