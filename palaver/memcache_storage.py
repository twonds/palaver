# Copyright (c) 2005 - 2008  Christopher Zorn, OGG, LLC 
# See LICENSE.txt for details
import memcache
import time
from twisted.internet import defer, reactor
from twisted.python import log
from twisted.words.protocols.jabber import jid
from zope.interface import implements
from twisted.python import threadpool
from twisted.internet import defer, threads
import thread, threading
import cPickle as pickle

def StorageError(Error):
    pass

# maybe move groupchat
import groupchat
import storage


class deferedThreadPool(threadpool.ThreadPool):
    """
    Extended ThreadPool that defers memcache tasks.
    """

    def deferToThread(self, func, *args, **kwargs):
        d = defer.Deferred()
        self.callInThread(threads._putResultInDeferred, d, func, args, kwargs)
        return d
    
    

class Storage:

    implements(storage.IStorage)
    sadmins = []

    def __init__(self, MEMCACHE_SERVERS):
        self.threadID = thread.get_ident
 	self.MEMCACHE_SERVERS = MEMCACHE_SERVERS
        
        
        # connect to memcache servers
        self.mc_connections = {}

        # self.threadpool = deferedThreadPool(10, 10)

        # need to start up thread pools
        self.running = False
        from twisted.internet import reactor
        self.startID = reactor.callWhenRunning(self._start)
        self.shutdownID = None
        

    def _start(self):
        self.startID = None
 	
        if not self.running:
             	    
            self.shutdownID = reactor.addSystemEventTrigger('during',
                                                            'shutdown',
                                                            self._finalClose)
            self.running = True

        
    def _flush(self):
        # flush the cache at component startup
        if len(self.MEMCACHE_SERVERS) > 0:
            mc = memcache.Client(self.MEMCACHE_SERVERS)
            mc.flush_all()
 	
    def _finalClose(self):
        """This should only be called by the shutdown trigger."""
        
        # the following works around issues with trial and reactor
        # starts.  see twisted bug #2498
        
        self.shutdownID = None
        
        self.startID = None
	
        # tear down memcache connections
        for mc in self.mc_connections.values():
            mc.disconnect_all()
        self.mc_connections.clear()
 	           
        self.running = False
 	
    def getMemcacheConnection(self):
        if len(self.MEMCACHE_SERVERS) == 0:
            return None
 	
        tid = self.threadID()
        mc = self.mc_connections.get(tid)
        if not mc:
            mc = memcache.Client(self.MEMCACHE_SERVERS, debug=0)
            self.mc_connections[tid] = mc
             	
        return mc
 	
    def getFromCache(self, key):
        mc = self.getMemcacheConnection()
        if mc:
            val = mc.get(key.encode('ascii','xmlcharrefreplace'))
            if val:
                return pickle.loads(val)
        return None
 	   
    def setInCache(self, key, val, expire=None):
        mc = self.getMemcacheConnection()
        if not mc:
            return
        # default is to cache for 24 hours
        if not expire:
            expire = int(time.time() + 86400)
        
        mc.set(key.encode('ascii','xmlcharrefreplace'), pickle.dumps(val), expire)

    def deleteInCache(self, key):
        mc = self.getMemcacheConnection()
        if not mc:
            return
        mc.delete(key)        
  
    def _getRoomFromCache(self, room, host = ''):
        return self.getFromCache(u"muc_room:"+room.lower()+host.lower())
        
    def _setRoom(self, room, val, host =''):
        self.setInCache(u"muc_room:"+room.lower()+host.lower(), val)
        list = self._getRoomList(host)
        if list:
            list[room] = True
        else:
            list = {room:True}
        self._setRoomList(room, list, host)
        

    def _deleteRoom(self, room, host = ''):
        self.deleteInCache(u"muc_room:"+room.lower()+host.lower())
        roster = self._getRosterList(room, host)
        self._deleteRosterList(room, host)
        for u in roster:
            self._clear_affiliations(room, u, host)
            self._deleteRoster(room, u, host)

        # grab room list
        list = self._getRoomList(host)
        if not list:
            list = {}
        if list.has_key(room.lower()):
            del list[room.lower()]
        self._setRoomList(host, list)
        
    def _getRoomList(self, host=''):
        list = []
        l = self.getFromCache(u"muc_rooms_list:"+host.lower())
        if l:
            list = l
        return list

    def _setRoomList(self, room, val, host =''):
        self.setInCache(u"muc_rooms_list:"+room.lower()+host.lower(), val)
        

    def _deleteRoomList(self, room, host = ''):
        self.deleteInCache(u"muc_rooms_list:"+room.lower()+host.lower())


    def _getRoster(self, room, user, host = ''):
        return self.getFromCache(u"muc_room_roster:"+room.lower()+user.lower()+host.lower())
        
    def _setRoster(self, room, user, val, host =''):
        self.setInCache(u"muc_room_roster:"+room.lower()+user.lower()+host.lower(), val)
        list = self._getRosterList(room, host)
        if list:
            list.append(user)
        else:
            list = [user]
        self._setRosterList(room, list, host=host)

    def _deleteRoster(self, room, user, host = ''):
        self.deleteInCache(u"muc_room_roster:"+room.lower()+user.lower()+host.lower())
        list = self._getRosterList(room, host)
        if list:
            list.pop(list.index(user))
        else:
            list = []
        self._setRosterList(room, list, host=host)


    def _getRosterList(self, room, host = ''):
        list = []
        l = self.getFromCache(u"muc_rooms_roster_list:"+room.lower()+host.lower())
        if l:
            list = l
        return list
        
    def _setRosterList(self, room, val, host =''):
        self.setInCache(u"muc_rooms_roster_list:"+room.lower()+host.lower(), val)
        

    def _deleteRosterList(self, room, host = ''):
        self.deleteInCache(u"muc_rooms_roster_list:"+room.lower()+host.lower())


    def _getAffiliationFromCache(self, room, user, host = ''):
        return self.getFromCache(u"muc_room_affiliation:"+room.lower()+user.lower()+host.lower())
        
    def _setAffiliationInCache(self, room, user, val, host =''):
        self.setInCache(u"muc_room_affiliation:"+room.lower()+user.lower()+host.lower(), val)
        

    def _deleteAffiliationInCache(self, room, user, host = ''):
        self.deleteInCache(u"muc_room_affiliation:"+room.lower()+user.lower()+host.lower())

    def _setRoomAffiliation(self, room, affiliation, val, host=''):
        self.setInCache(u"muc_room_affiliation:"+affiliation+":"+room.lower()+host.lower(), val)
    
    def _getRoomAffiliation(self, room, affiliation, host = ''):
        a = self.getFromCache(u"muc_room_affiliation:"+affiliation+":"+room.lower()+host.lower())
        if not a:
            a = {}
        return a

    def _deleteRoomAffiliation(self, room, affiliation, host=''):
        self.deleteInCache(u"muc_room_affiliation:"+affiliation+":"+room.lower()+host.lower())

    def _getRoom(self, room, host=''):
        r = self._getRoomFromCache(room, host)
        if r:
            r['roster'] = self._get_room_members(room, host)
            r['reason'] = {}
            for a in groupchat.AFFILIATION_LIST:
                r[a] = self._getRoomAffiliation(room, a, host)

        return r

    def _roomExists(self, room, host=''):
        # NEED  test to make sure this is not in the main thread
        r = self._getRoomFromCache(room, host)
        if r != None:
            return True
        return False
    
    def createRoom(self, room, owner, **kwargs):
        """
        create a room and put it in memcache
        """
        host = kwargs['host']
        def create():
            if self._roomExists(room):
                raise groupchat.RoomExists
            room_dict                   = {}
            room_dict['name']           = room
            room_dict['roomname']       = room
            room_dict['subject']        = ''
            room_dict['subject_change'] = True
            room_dict['persistent']     = False
            room_dict['moderated']      = False
            room_dict['private']        = True
            room_dict['history']        = 10
            room_dict['game']           = False
            room_dict['inivtation']     = False
            room_dict['invites']        = True
            room_dict['hidden']         = False
            room_dict['privacy']        = False
            room_dict['locked']         = True
            room_dict['subjectlocked']  = False
            room_dict['description']    = room
            room_dict['leave']          = ''
            room_dict['join']           = ''
            room_dict['rename']         = ''
            room_dict['maxusers']       = 30
            room_dict['privmsg']        = True
            room_dict['change_nick']    = True
            room_dict['query_occupants']= False
            

            # is there a better way to do this?
            for arg in kwargs:
                if arg == 'legacy':
                    if kwargs[arg]:
                        room_dict['locked'] = False
                else:
                    room_dict[arg] = kwargs[arg]
            self._setRoom(room, room_dict, host=host)
            for a in groupchat.AFFILIATION_LIST:
                room_dict[a] = {} 
                if a == 'owner':
                    jowner = jid.internJID(owner).userhost()
                    # affiliations are tuples, (affiliation, reason)
                    aval = (a,'creator')
                    room_dict[a][jowner] = jowner
                    self._setAffiliationInCache(room, jowner, aval, host=host)
                
                self._setRoomAffiliation(room, a, room_dict[a], host)

            return room_dict

        return threads.deferToThread(create)

    
    def setRole(self, room, user, role, host=''):    
        return threads.deferToThread(self._set_role, room, user, role, host=host)

        
    def _set_role(self, room, user, role, host=''):
        r = self._getRoster(room, user, host)
        user = user.lower()
        if r:
            self._setRoster(room, user, r, host=host)
            return True
        else:
            raise groupchat.RoomNotFound
        
    
    def getRole(self, room, user, host=''):
        def role():
            role = None
            u = self._getRoster(room, user, host=host)
            if u:
                role = u['role']
                return role
            
        return threads.deferToThread(role)


    def setAffiliation(self, room, user, affiliation, reason=None, host=''):
        return threads.deferToThread(self._set_affiliation, room, user, affiliation, reason=reason, host=host)
        
        
    def _set_affiliation(self, room, user, affiliation, reason=None, host=''):        
        user = user.lower()
        r = self._getRoomFromCache(room, host)
        if r:
            self._clear_affiliations(room, user, host)
            a_list = self._getRoomAffiliation(room, affiliation, host)
            a_list[user] = user
            self._setRoomAffiliation(room, affiliation, a_list, host)
            if not reason:
                reason = affiliation
            self._setAffiliationInCache(room, user, (affiliation, reason), host=host)

        else:
            raise groupchat.RoomNotFound
        

    

    def getAffiliation(self, room, user, host=''):
        return threads.deferToThread(self._getAffiliation, room, user, host)

    
    def _getAffiliation(self, room, user, host = ''):
        affiliation = 'none'
        ju = jid.internJID(user).userhost()
        
        a = self._getAffiliationFromCache(room, ju, host)
        if a:
            return a[0]
        a = self._getAffiliationFromCache(room, user, host)
        if a:
            return a[0]        
        return affiliation
                

    def joinRoom(self, room, user, nick, status = None, show=None, legacy=True, host=''):
        def join():
            r = self._getRoomFromCache(room, host)
            new_user = None
            # find user
            
            if r:
                new_user = self._getRoster(room, user, host)
            else:
                raise groupchat.RoomNotFound
                
            if new_user:
                log.msg('Already in roster?')
         
            else:
                u = {}
                                
                u['jid']  = user
                u['affiliation'] = self._getAffiliation(room, user, host)
                
                if r['moderated']:
                    role = 'visitor'
                else:
                    role = groupchat.AFFILIATION_ROLE_MAP[u['affiliation']]

                u['role'] = role
                u['nick'] = nick
                u['legacy'] = legacy
                u['show'] = show
                u['status'] = status

                self._setRoster(room, user, u, host=host)

            return True
        
        return threads.deferToThread(join)
        

    def partRoom(self, room, user, nick, host=''):
        def part(user, nick):
            # check for room types, grab role and affiliation
            nick = nick.lower()
            old_u = None
            user_check = user.lower()
            roster_list = self._getRosterList(room, host)
            for ruser in roster_list:
                if ruser.lower() == user_check or \
                        jid.internJID(ruser).userhost().lower() == user_check:
                    old_u = self._getRoster(room, ruser, host)
                    break

            if old_u:
                self._deleteRoster(room, old_u['jid'], host)
                return old_u

        return threads.deferToThread(part, user, nick)


    def _get_room_members(self,  room, host=''):
        members = {}
        r = self._getRoomFromCache(room, host)
        if r:
            roster = self._getRosterList(room, host)
            for u in roster:
                uval = self._getRoster(room, u, host)
                if uval:
                    members[u] = uval
                else:
                    roster.pop(roster.index(u))
        return members
        
    def getRoomMembers(self, room, host='', frm=None):
        return threads.deferToThread(self._get_room_members, room, host)
    

    def deleteRoom(self, room, owner = None, check_persistent = False, host=''):
        def delete():
            r = self._getRoomFromCache(room, host)
            if check_persistent and r:
                p = r['persistent']            
                if p:
                    return False
        
            if r:
                self._deleteRoom(room, host)
            return True

        return threads.deferToThread(delete)


    def setOwner(self, room, user, host = ''):
        return self.setAffiliation(room, user, 'admin', host=host) 

    def setOutcast(self, room, user, reason, host = ''):
        return self.setAffiliation(room, user, 'outcast', reason, host=host) 

    def setPlayer(self, room, user, host = ''):
        return self.setAffiliation(room, user, 'player', host=host) 


    def setAdmin(self, room, user, host = ''):
        return self.setAffiliation(room, user, 'admin', host=host) 


    def _clear_affiliations(self, room, user, host = ''):
        self._deleteAffiliationInCache(room, user, host)
        for affiliation in groupchat.AFFILIATION_LIST:
            a_list = self._getRoomAffiliation(room, affiliation, host)
            if user in a_list:
                del a_list[user]
            self._setRoomAffiliation(room, affiliation, a_list, host)

    def setMember(self, room, user, host = ''):
        return self.setAffiliation(room, user, 'member', host=host) 

    def changeNick(self, room, user, nick, host = ''):
        def nick():
            user = user.lower()
            r = self._getRoomFromCache(room, host)
            if r:
                u = self._getRoster(room, user, host)
                u['nick'] = nick
                self._setRoster(room, user, u, host)
                return nick
            else:
                raise groupchat.RoomNotFound

        return threads.deferToThread(nick)

    def getNicks(self, room, host =''):
        def get():
            nicks = []
            r = self._getRoomFromCache(room, host)
            if r:
                for u in self._get_room_members(room, host).values():
                    nicks.append(u['nick'])
            return nicks

        return threads.deferToThread(get)
    
    def _updateRoom(self, room, **kwargs):
        r = self._getRoomFromCache(room, kwargs['host'])        
        if r:
            # is there a better way to do this?
            try:
                for arg in kwargs:
                    r[arg] = kwargs[arg]
                self._setRoom(room, r, host=kwargs['host'])
                return r
            except:
                log.err()
                raise groupchat.RoomNotFound
        else:
            raise groupchat.RoomNotFound
 
    def updateRoom(self, room, **kwargs):
        return threads.deferToThread(self._updateRoom, room, **kwargs)


    def getRoom(self, room, host = '', frm = None):
        return threads.deferToThread(self._getRoom, room, host)


    def _get_rooms(self, host = '', frm=None):
        ret = []
        room_list = self._getRoomList(host=host)
        for r in room_list:
            ret.append(self._getRoom(r, host))
        return ret

    def getRooms(self, host = '', frm = None):
        return threads.deferToThread(self._get_rooms, host=host, frm=frm)
    
    def changeStatus(self, room, user, show = None, status = None, legacy=True, host = ''):
        return threads.deferToThread(self._changeStatus, room, user, 
                                             show=show, 
                                             status=status, 
                                             legacy=legacy, 
                                             host = host)
    
    def _changeStatus(self, room, user, show = None, status = None, legacy=True, host = ''):                       
        r = self._getRoomFromCache(room, host)
        user = user.lower()
        if r:
            u = self._getRoster(room, user, host)
            u['show'] = show
            u['status'] = status
            u['legacy'] = legacy
            self._setRoster(room, user, u, host)
            return r
        else:
            raise groupchat.RoomNotFound

