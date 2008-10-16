"""
 Copyright (c) 2005-2008 Christopher Zorn, OGG, LLC 
 See LICENSE.txt for details
"""
from twisted.words.protocols.jabber import jid
from twisted.application import service
from twisted.internet import defer
from twisted.python import log


from zope.interface import Interface, implements
import datetime

from xmpp.ns import *

AFFILIATION_LIST = ['admin','member','owner','player','outcast']

AFFILIATION_ROLE_MAP = {
    'admin': 'moderator',
    'member': 'participant',
    'owner': 'moderator',
    'player': 'player',
    'outcast': 'none',
    'none': 'participant',
}

class Error(Exception):
    muc_error = None
    stanza_error = None
    msg = ''

class BadRequest(Error):
    pass

class RoomNotFound(Error):
    pass

class RoomExists(Error):
    pass

class NotAuthorized(Error):
    pass

class NotAllowed(Error):
    pass

class Forbidden(Error):
    pass


class NotMember(Error):
    pass

class NickConflict(Error):
    pass

class Unavailable(Error):
    pass

class InvalidConfigurationOption(Error):
    pass

class InvalidConfigurationValue(Error):
    pass

class IGroupchatService(Interface):

    """
    The multi-user service for multi-user chat
    """
    def getRooms(self, host = None, frm = None):
        """
        Get all rooms
        """

    def getRoom(self, room, host):
        """
        Get room
        """

    def getRoomMembers(self, room, host):
        """
        Get room members
        """

    def getMember(self, members, mid):
        """
        """

    def deleteRoom(self, room, host):
        """
        """

    def getHistory(self, room, host):
        """
        """

    def resetCache(self):
        """
        reset cache data
        """

    def resetHistory(self, room):
        """
        reset history messages 
        """

        
class IRoomService(Interface):
    """
    """
    def getRoom(self, room, host):
        """
        """
        
    def getRoomMembers(self, room, host):
        """
        """
        
    def createRoom(self, room, frm, nick, status = None, show=None, host=None):
        """
        """
        
    
    def deleteNonPersistentRoom(self, room, host):
        """
        """

    def processGroupChat(self, room, frm, body, host):
        """        
        """

    def partRoom(self, room, frm, nick, host):
        """
        """
        
    def getMember(self, members, user, host):
        """
        """

    def joinRoom(self, room, frm, nick, status = None, show=None, legacy=True, host=None):
        """
        joinRoom
        
        """
        

    def invite(self, room, to, frm, host):
        """
        """

    def checkNick(self, room, nick, host):
        """
        """
    
    def changeNick(self, room, user, nick, host):
        """
        """

    def changeSubject(self, room, frm, subject, host):
        """
        """

    def changeStatus(self, room, user, show = None, status = None, legacy=True, host=None):
        """
        """

    # TODO - room registration
        
        
class IAdminService(Interface):
    """
    """
    def getRoom(self, room, admin, host):
        """
        """

    def getRoomConfig(self, room, admin, host):
        """
        """

    def getRoomMembers(self, room, admin, host):
        """
        """

    def getMember(self, room, user, host):
        """
        """

    def kick(self, user, room, admin, host):
        """
        """

    def ban(self, user, room, admin, reason, host):
        """
        """

    def grantMembership(self, user, room, admin, host):
        """
        """        

    def getModerators(self, admin, room, host):
        """
        """

    def grantAdmin(self, user, room, admin, host):
        """
        """
        

    def revokeAdmin(self, user, room, admin, host):
        """
        """


    def checkAdmin(self, room, user):
        """
        """

    def checkModerator(self, room, user):
        """
        """


    def getAdmins(self, room, admin, host):
        """
        """
    
    def getOutcasts(self, room, admin, host):
        """
        """
    
    def getMembers(self, room, admin, host):
        """
        """
    
    def getRoles(self, room, role, admin, host):
        """
        """
    
    def updateRoom(self, room, owner, **kwargs):
        """
        """
    
    def grantOwner(self, user, room, owner, host):
        """
        """

    def revokeOwner(self, user, room, owner, host):
        """
        """


    def getOwner(self, room, user, owner, host):
        """
        """


    def checkOwner(self, room, user, host):
        """
        """


    def getOwners(self, room, owner, host):
        """
        """


    def destroyRoom(self, room, user, host):
        """
        """



class GroupchatService(service.MultiService):
    """
    MUC Groupchat Service
    """
    implements(IGroupchatService)

    HISTORY = {}
    sadmins = []
    plugins = {}
    
    def __init__(self, storage, use_cache = False):
        service.MultiService.__init__(self)
        self.use_cache = use_cache
        self.storage = storage
        
        self.storage.use_cache = use_cache

        self.active_rooms = []


    def resetCache(self):
        try:
            self.storage.resetCache()
        except:
            pass

    def resetHistory(self, room=None, frm=None):
        if room != None:
            # room needs to be a returned room hash from the backend
            if self.checkAdmin(room, jid.internJID(frm).userhost()):
                self._clean_up_history(True, room['name'])
        elif jid.internJID(frm).userhost() in self.sadmins:
            self.HISTORY = {}
    
    def getActiveRoom(self, name):
        idx = self.active_rooms.index(name) 
        if idx != -1:
            return self.active_rooms[idx]
        
    def addActiveRoom(self, name):
        idx = self.active_rooms.index(name) 
        if idx == -1:
            self.active_rooms.append(name)

    def removeActiveRoom(self, name):
        idx = self.active_rooms.index(name) 
        if idx != -1:
            self.active_rooms.pop(idx)
        
    def getRooms(self, host = None, frm = None):
        # do we need a call back from processing the rooms?
        return self.storage.getRooms(host = host, frm = frm)

    def getRoom(self, room, host = None, frm = None):
        return self.storage.getRoom(room, host = host, frm = frm)

    def getRoomMembers(self, room, host = None):
        return self.storage.getRoomMembers(room, host = host)

    def getMember(self, members, mid, host=None):
        """
        grab the member from the roster list.
 
        """
        ret_m = members.get(mid)
        if not ret_m:
            ret_m = members.get(mid.lower())
        if not ret_m:
            ret_mem = members.get(jid.internJID(mid).userhost())
        if not ret_m:
            ret_mem = members.get(jid.internJID(mid).userhost().lower())

        return ret_m

    def deleteRoom(self, room, host=None):
        self._clean_up_history(True, room)
        return self.storage.deleteRoom(room, host=host)

    def _clean_up_history(self, do_it, room):
        if do_it:
            if self.HISTORY.has_key(room.lower()):
                del self.HISTORY[room]

    def getHistory(self, room, host=None):
        """
        """
        if self.HISTORY.has_key(room.lower()):
            return self.HISTORY[room.lower()]


    def checkOwner(self, room, user):
        if self._check_sadmin(room, user):
            return True
        if self._check_owner(room, user):
            return True

        return False


    def checkModerator(self, room, user):
        if self._check_sadmin(room, user):
            return True
        if self._check_owner(room, user):
            return True
        if self._check_admin(room, user):
            return True
        if self._check_role(room, user, 'moderator'):
            return True
            
        return False


    def checkBanned(self, room, user):
        check = False
        juser = jid.internJID(user).userhost()
        members = room.get('outcast', {})
        if members.has_key(user):
            check = True
            return check
        if members.has_key(juser):
            check = True
            return check
        if members.has_key(user.lower()):
            check = True
            return check
        if members.has_key(juser.lower()):
            check = True
            return check

        return check


    def checkAdmin(self, room, user):
        if self._check_sadmin(room, user):
            return True
        if self._check_owner(room, user):
            return True
        if self._check_admin(room, user):
            return True
        
        return False


    def checkMember(self, room, user):
        if self._check_sadmin(room, user):
            return True
        if self._check_owner(room, user):
            return True
        if self._check_admin(room, user):
            return True
        
        return self._check_member(room, user)

    def _check_sadmin(self, room, user):
        juser = jid.internJID(user).userhost().lower()
        members = self.sadmins
        for m in members:
            if jid.internJID(m).userhost().lower() == juser:
                return True
        return False
    
    def _check_owner(self, room, user):
        check = False
        juser = jid.internJID(user).userhost()
        members = room.get('owner', {})

        if members.has_key(user):
            check = True
            return check
        if members.has_key(juser):
            check = True
            return check
        if members.has_key(user.lower()):
            check = True
            return check
        if members.has_key(juser.lower()):
            check = True
            return check        

        return check

    def _check_admin(self, room, user):
        check = False
        juser = jid.internJID(user).userhost()
        members = room.get('admin', {})
        if members.has_key(user):
            check = True
            return check
        if members.has_key(juser):
            check = True
            return check
        if members.has_key(user.lower()):
            check = True
            return check
        if members.has_key(juser.lower()):
            check = True
            return check                
        return check

    def _check_member(self, room, user):
        check   = False
        juser   = jid.internJID(user).userhost()
        members = room.get('member', {})
        players = room.get('players', {})
        roster  = room.get('roster', {})
        for members in [members, roster, players]:
            if members.has_key(user):
                check = True
                return check
            if members.has_key(juser):
                check = True
                return check
            if members.has_key(user.lower()):
                check = True
                return check
            if members.has_key(juser.lower()):
                check = True
                return check                
        return check

class RoomService(service.Service):

    implements(IRoomService)
    
    create_rooms = 1    
    sadmins = []
    plugins = {}

    def setUpHistory(self, host):
        self.parent.getRooms(host).addCallback(self._cbSetUpHistory, host)
        
    def _cbSetUpHistory(self, rooms, host):
        for r in rooms:
            if not r['name']:
                continue
            if not self.parent.HISTORY.has_key(r['name'].lower()):
                self.parent.HISTORY[r['name'].lower()] = []
                if self.parent.use_cache:
                    self.getRoom(r['name'], host)
                    
    def getRoom(self, room, host=None):
        return self.parent.getRoom(room, host = host)

    def getRoomMembers(self, room, host=None):
        return self.parent.getRoomMembers(room, host = host)
        

    def getHistory(self, room, host=None):
        return self.parent.getHistory(room, host = host)
        
    def createRoom(self, room, frm, nick, status = None, show = None, legacy = True, host=None):
        """
        Create and join the room
        """

        def created(rname):
            self.parent.HISTORY[room] = []
            return self.joinRoom(room, frm, nick,
                                 status = status,
                                 show   = show,
                                 legacy = legacy,
                                 host   = host,
                                 do_check = False)

        def create_room(doCreate, error_code=NotAllowed):
            if not doCreate:
                raise error_code
            
            d = self.parent.storage.createRoom(room, jid.internJID(frm).userhost(), legacy=legacy, host=host)
            d.addCallback(created)
            return d

        if self.create_rooms == 1 or jid.internJID(frm).userhost() in self.sadmins:
            if self.plugins and self.plugins.has_key('create-room'):
                d = self.plugins['create-room'].create(room, jid.internJID(frm).userhost(), legacy=legacy, host=host)
                d.addCallback(create_room, error_code = NotMember)
            else:
                d = create_room(True)
            
            return d
        else:
            raise NotAllowed


    def deleteNonPersistentRoom(self, room, host=None):
        d = self.parent.storage.deleteRoom(room, check_persistent = True, host = host)
        d.addCallback(self.parent._clean_up_history, room)
        return d
    
    def processGroupChat(self, room, frm, body, extra=[], host=None):
        
        def process(r):
            if r is None:
                raise RoomNotFound
            members = r['roster']
            if self.checkBanned(r, frm):
                raise Forbidden                
            user = self.getMember(members, frm)
            if frm in self.sadmins:
                if user:
                    nick = user['nick']
                else:
                    nick = frm
                user = {'jid': frm,
                        'role': 'moderator',
                        'affiliation': 'owner',
                        'nick': nick,
                        }

            if user is None:
                log.msg(frm)
                log.msg(members)
                log.msg('User is none, something is wrong')
                raise NotAuthorized
            
            if r['locked']:
                raise RoomNotFound

            if (user['role'] == 'visitor' or user['role']=='none') \
                   and r['moderated']:
                return
            if user['role'] == 'none' and user.has_key('affiliation') and user['affiliation'] == 'outcast':
                raise Forbidden
            if user['role'] == 'none':
                raise NotAuthorized
            

            if r.has_key('message_size') and not int(r['message_size'])==0 and int(r['message_size']) < len(body.__str__()):
                raise Unavailable
    
            if not self.parent.HISTORY.has_key(room):
                self.parent.HISTORY[room] = []
            hist = {}

            hist['body']  = body
            hist['extra'] = extra
            hist['user']  = user
            # CCYYMMDDThh:mm:ss
            #hist['stamp'] = datetime.datetime.now().strftime('%Y%m%dT%H:%m:%S')
            hist['stamp'] = datetime.datetime.utcnow()
            
            if len(members)>0 and body != '' and body is not None:
                self.appendHistory( room, r['history'], hist)
            
            return r, user
        ep = None
        if getattr(self, 'plugins'):
            ep = self.plugins.get('groupchat')
        if ep:
            d = ep.message(frm, body)
            d.addErrback(lambda x: self.error(NotAllowed, x)) 
            d.addCallback(lambda _: self.getRoom(room, host = host))
        else:
            d = self.getRoom(room, host = host)
        d.addCallback(process)
        return d
        
        
    def appendHistory(self, room, maxsize, hist):
        if len(self.parent.HISTORY[room])>int(maxsize):
            self.parent.HISTORY[room].pop(0)
        self.parent.HISTORY[room].append(hist)

    def partRoom(self, room, frm, nick, host=None):
        def return_room_tup(r, u, frm, nick):
            frm = frm.lower()
            nick = nick.lower()
            if not r:
                raise RoomNotFound
            else:
                members = r['roster']
            
            if not r['persistent'] and len(members)==0:
                # delete the room if not persistent
                self.deleteNonPersistentRoom(room, host)
            else:
                if r['locked']:
                    raise RoomNotFound

                for usr in r['roster'].values():
                    try:
                        if usr['jid'].lower() == frm or usr['nick'].lower() == nick:
                            r['roster'][usr['jid'].lower()]['role'] = 'none'
                            break
                    except:
                        log.err()
            
            return (r, u)

        def ret(u):
            d = self.getRoom(room, host = host)
            d.addCallback(return_room_tup, u, frm, nick)
            return d
                                
        d = self.parent.storage.partRoom(room, frm, nick, host)
        d.addCallback(ret)
        return d
             

    def getMember(self, members, user, host=None):
        return self.parent.getMember(members, user)

    def checkBanned(self, room, user):
        return self.parent.checkBanned(room, user)
    
    def joinRoom(self, room, frm, nick, status = None, show = None, legacy = True, host = None, do_check = True):
        """
        joinRoom
        
        """

        def ret_room_user(r):
            u = r['roster'].get(frm)
            if not u:
                log.msg('join room did not find user in roster')
                u = r['roster'].get(frm.lower())
            return r, u

        def ret_room(t):
            if t:
                return self.getRoom(room, host = host).addCallback(ret_room_user)
            else:
                raise RoomNotFound
            
            
        def join(check, u):
            
            if check:
                raise NickConflict
            else:
                d = self.parent.storage.joinRoom(room, frm, nick,
                                                 status = status,
                                                 show   = show,
                                                 legacy = legacy,
                                                 host   = host)
                d.addCallback(ret_room)
                return d
            
        def ret(r):
            if not r:
                raise Unavailable
            
            if int(r['maxusers']) > 1 and int(r['maxusers'])<=len(r['roster']):
                raise Unavailable

            
            members = r['roster']
            
            d = None
            user = self.getMember(members, frm)
            
            if r['locked'] and user is None and do_check:
                raise RoomNotFound

            if user is None:
                if r.has_key('invitation') and r['invitation']:
                    # TODO - this needs to be a method
                    found_member = False
                    if not self.checkMember(r, frm):
                        raise NotAuthorized
                
                if self.checkBanned(r, frm):
                    raise Forbidden


                d = self.checkNick(room, nick, host)
                d.addCallback(join, user)
                return d
            else:
                log.msg('groupchat: Error here?')
                

        def get_room(doGet):
            if not doGet:
                raise NotMember
            
            d = self.getRoom(room, host = host)
            # join room plugin
            d.addCallback(ret)
            return d
        
        if self.plugins and self.plugins.has_key('join-room'):
            # d.addCallback(self.plugins['join-room'].join)
            d = self.plugins['join-room'].join(jid.internJID(frm).userhost(), room, host)
            d.addCallback(get_room)
            
        else:
            d = get_room(True)
            
        return d


    def checkAdmin(self, room, user):
        return self.parent.checkAdmin(room, user)


    def checkMember(self, room, user):
        return self.parent.checkMember(room, user)

    def _check_role(self, room, user, role):
        cr = False
        u = room['roster'].get(user)
        if not u:
            u = room['roster'].get(user.lower())
        if u and u['role'] == role:
            cr = True
        return cr


    def checkModerator(self, room, user):
        return self.parent.checkModerator(room, user)


    def checkNick(self, room, nick, host=None):
        def check(nicks, nick):
            nick = nick.lower()
            for n in nicks:
                if nick == n.lower():
                    return True
            return False
        
        d = self.parent.storage.getNicks(room,host=host)
        d.addCallback(check, nick)
        return d
    
    def changeNick(self, room, user, nick, host=None):
        def new_nick(ret):
            return self.getRoom(room['name'], host)
        
        def check_nick(check):
            
            if check:
                raise NickConflict
            else:
                d = self.parent.storage.changeNick(room['name'], user['jid'], nick,host=host)
                d.addCallback(new_nick)
                return d
            
        # check if we can change nick
        if room['change_nick']:
            d = self.checkNick(room['name'], nick, host)
            d.addCallback(check_nick)
            return d
        else:
            raise NotAuthorized

    def error(self, error, emsg=None):
        
        raise error

    def changeSubject(self, room, frm, subject, host=None):
        
        def success(row, r, user):
            return r, user
        
        def change(r):
            members = r['roster']
            user = self.getMember(members, frm, host = host)
            allow_update = True
            if not r['subject_change']:
                # grab members
                if user['role'] != 'moderator':
                    allow_update = False
                
            if allow_update or user['role'] == 'moderator':
                d = self.parent.storage.updateRoom(room, subject = subject, host=host)
                d.addCallback(success, r, user)
                d.addErrback(lambda x : self.error(RoomNotFound)) 
                return d
            else:
                raise NotAllowed
        # TODO - raise an error            
        
        
        # grab room
        d = self.getRoom(room, host = host)
        d.addCallback(change)
        return d

    def changeStatus(self, room, user, show = '', status = '', legacy = True, host=None):
        def success(t):
            if t:
                return self.getRoom(room, host)

        if status is None:
            status = ''
        if show is None:
            show = ''
        d = self.parent.storage.changeStatus(room, user, show, status, legacy, host = host)
        d.addCallback(success)

        d.addErrback(lambda x : self.error(NotMember)) 
        return d



class AdminService(service.Service):

    implements(IAdminService)
    plugins = {}
    sadmins = []

    def error(self, error, emsg=None):

        raise error

    def getRoom(self, room, admin, host=None):
        def get(r):
            if r and self.checkAdmin(r, admin):
                return r
            
            else:
                raise NotAllowed

        d =  self.parent.getRoom(room, host=host)
        d.addCallback(get)
        return d

    def getRoomConfig(self, room, admin, host=None):
        def get(r):
            if r and self.checkOwner(r, admin):
                return r
            else:
                raise NotAllowed

        d = self.parent.getRoom(room, host=host)
        d.addCallback(get)
        return d

    

    def getRoomMembers(self, room, admin = None, host=None):
        def get(r):
            if r and self.checkAdmin(r, admin):
                return r['roster']
            else:
                raise NotAllowed
        d =  self.parent.getRoomMembers(room, host=host)
        if admin:
            d.addCallback(get)
        return d


    def resetCache(self):
        reset = False
        try:
            reset = self.parent.storage.resetCache()
        except:
            log.err()
            pass
        return reset

    def resetHistory(self, room=None, frm=None):
        if room != None:
            # room needs to be a returned room hash from the backend
            if self.checkAdmin(room, jid.internJID(frm).userhost()):
                self.parent._clean_up_history(True, room['name'])
        elif jid.internJID(frm).userhost() in self.sadmins:
            self.HISTORY = {}



    def getMember(self, room, user, host = None):
        return self.parent.getMember(room, user, host = host)

    def kick(self, user, room, admin, host=None):
        """
        """
        def ret_kick(rooms, room, old_r):
            return old_r
        
        def set_kick(r, user):
            if self.checkAdmin(r, admin):
                kuser = None
                roster = []
                if self.checkOwner(r, user):
                    raise NotAllowed
                user_check = jid.internJID(user).userhost().lower()
                for u in r['roster'].values():
                    if jid.internJID(u['jid']).userhost().lower() == user_check \
                           or u['nick'] == user:
                        kuser = u['jid']
                        knick = u['nick']
                        if self.checkSelf(user, admin):
                            raise NotAllowed
                        
                        if self.checkAdmin(r, user):
                            raise NotAllowed
                        r['roster'][u['jid'].lower()]['role'] = 'none'
                        r['roster'][u['jid'].lower()]['affiliation'] = 'none'
                        break
                if not kuser:
                    raise RoomNotFound
                d = self.parent.storage.partRoom(room, kuser, knick, host=host)
                d.addCallback(ret_kick, room, r['roster'])
                d.addErrback(lambda x: self.error(NotAllowed, x)) 
                return d
            else:
                raise NotAllowed
        
        d = self.parent.storage.getRoom(room,host=host)
        d.addCallback(set_kick,user)
        return d

    def ban(self, user, room, admin, reason=None, host=None):
        """
        """
        def part_room(rooms, buser, unick):
            if buser:
                d = self.parent.storage.partRoom(room, buser, unick, host = host)
                d.addCallback(lambda _: rooms)
                return d
            else:
                return rooms

        def ret_ban(rooms, room, old_r):
            return old_r
        
        def set_ban(r, user):
            if not r:
                raise RoomNotFound
            
            if self.checkAdmin(r, admin):
                
                if self.checkSelf(user, admin):
                    # you can not ban yourself
                    raise NotAllowed
                
                if self.checkAdmin(r, user):
                    # you can not ban an admin
                    raise NotAllowed

                if self.checkBanned(r, user):
                    # you can not ban some already banned
                    d =  defer.succeed(r)
                    d.addCallback(ret_ban, room, r['roster'])
                    d.addErrback(lambda x:self.error(NotAllowed, x)) 
                    return d
                
                user_check = jid.internJID(user).userhost().lower()
                unick = 'none'
                ban_user = None

                for u in r['roster'].values():
                    ujid = jid.internJID(u['jid']).userhost().lower()
                    if ujid == user_check or u['nick'] == user:
                        unick = u['nick']
                        r['roster'][u['jid'].lower()]['role'] = 'none'
                        r['roster'][u['jid'].lower()]['affiliation'] = 'outcast'
                        ban_user = u['jid']
                        break

                # We want to outcast the current user given but make sure we leave the room 
                # with the user in the roster. 
                d = self.parent.storage.setOutcast(room, user, reason = reason, host = host)
                d.addCallback(part_room, ban_user, unick)
                d.addCallback(ret_ban, room, r['roster'])
                d.addErrback(lambda x: self.error(NotAllowed, x)) 
                #d.addErrback(lambda x: log.err(x))
                return d
            else:
                raise NotAllowed
        
        d = self.parent.storage.getRoom(room, host=host)
        d.addCallback(set_ban, user)
        #d.addErrback(lambda x: self.error(NotAllowed, x)) 
        d.addErrback(lambda x: log.err(x))
        return d

    def grantRole(self, role, user, room, admin, host=None):
        """
        """        
        def set_r(r, user, role):
            if r is None:
                log.msg('Role can not be granted ' + room + user)
                raise NotAllowed
            check = self.checkAdmin
            if role == 'none' or role == 'participant':
                check = self.checkModerator
            
            if check(r, admin):
                user_check = user.lower()
                ru = None
                # TODO - clean this up
                roster = r['roster']
                cjid = None
                for m in r['roster'].values():
                    if m['jid'].lower() == user_check or m['nick'].lower() == user_check:
                        if self.checkSelf(m['jid'], admin):
                            raise NotAllowed
                                           
                        cjid = m['jid']
                        roster[cjid.lower()]['role'] = role
                        break
                if cjid:
                    d = self.parent.storage.setRole(room, cjid, role, host=host)
                    d.addCallback(lambda _: roster)
                    return d
                return roster
            else:
                raise NotAllowed
        
        d = self.parent.storage.getRoom(room, host=host)
        d.addCallback(set_r, user, role)
        return d


    def grantMembership(self, user, room, admin, host=None):
        """
        """
        def set_member(r, user):
            mjid = None
            if r == None:
                raise RoomNotFound
            
            if self.checkAdmin(r, admin):
                juser = jid.internJID(user)
                
                # TODO - clean this up
                roster = r['roster']
                set_role = False
                
                for m in roster.values():
                    idx = m['jid'].lower()
                    rjid = jid.internJID(m['jid'])
                    if juser.resource:
                        mjids = rjid.full().lower()
                    else:
                        mjids = rjid.userhost().lower()
                        
                    if mjids == user.lower() or m['nick'].lower() == user.lower():
                        if self.checkSelf(m['jid'], admin):
                            raise NotAllowed
                        
                        # if self.checkAdmin(r, m['jid']):
                        #    raise NotAllowed
                        mjid = m['jid']
                        if roster[idx]['role'] == 'none' or \
                           roster[idx]['role'] == 'visitor' or \
                           roster[idx]['role'] == 'player':
                            roster[idx]['role'] = 'participant'
                            set_role = True
                        roster[idx]['affiliation'] = 'member'
                        break
                
                dlist = []
                if user:
                    # This sets it in storage
                    dm = self.parent.storage.setMember(room, user, host = host)
                    
                    dlist.append(dm)
                    
                if mjid and set_role:
                    # This sets it in the roster
                    dr = self.parent.storage.setRole(room, mjid, 'participant', host=host)
                    
                    dlist.append(dr)
                    
                    
                d = defer.DeferredList(dlist)
                d.addErrback(lambda x: self.error(NotAllowed, x))
                d.addCallback(lambda _: roster)
                return d
                
            else:
                raise NotAllowed
        
        d = self.parent.storage.getRoom(room, host=host)
        d.addCallback(set_member, user)
        d.addErrback(lambda x: self.error(NotAllowed, x)) 
        return d

    def clearAffiliation(self, user, room, admin, host=None):
        """
        """
        def clear_affiliation(r, user):
            mjid = None
            if self.checkAdmin(r, admin):
                roster = r['roster']
                
                for m in roster.values():
                    if m['jid'].lower() == user.lower() or m['nick'].lower() == user.lower():
                        if self.checkSelf(m['jid'], admin):
                            raise NotAllowed
                        
                        # if self.checkAdmin(r, m['jid']):
                        #    raise NotAllowed
                        mjid = m['jid']
                        
                        roster[mjid.lower()]['affiliation'] = 'none'
                        break
                if not mjid:
                    mjid = user
                # This sets it in the roster
                                        
                d = self.parent.storage.setAffiliation(room,
                                                       mjid,
                                                       'none',
                                                       host=host)
                d.addErrback(lambda x:self.error(NotAllowed,x))
                d.addCallback(lambda _: roster)
                return d
                
            else:
                raise NotAllowed
        
        d = self.parent.storage.getRoom(room, host=host)
        d.addCallback(clear_affiliation, user)
        return d    


    def getModerators(self, admin, room, host=None):
        """
        """
        def get_moderators(r):
            return r['admin']
        
        d = self.parent.storage.getRoom(room, host=host)
        d.addCallback(get_moderators)
        return d


    def destroyRoom(self, room, user, host=None):
        def destroy(r):
            try:
                if self.checkOwner(r, user):
                    
                    return self.parent.deleteRoom(room, host=host)
                else:
                    raise NotAllowed
            except:
                raise RoomNotFound
            
        d = self.parent.storage.getRoom(room, host=host)
        d.addCallback(destroy)
        return d

    def revokeAdmin(self, user, room, admin, host=None):
        """
        """
        def del_admin(r):
            if self.checkAdmin(r, admin):
                                
                for m in r['roster'].values():
                    if m['jid'].lower() == user.lower() or m['nick'] == user:
                        if self.checkSelf(m['jid'], admin):
                            raise NotAllowed
                        
                        user = jid.internJID(m['jid']).userhost()
                        break
                        
                if user in r['admin']:
                    del r['admin'][user]
                return r['roster']
            else:
                raise NotAllowed
        d = self.parent.storage.getRoom(room, host=host)
        d.addCallback(del_admin)
        return d

    def checkSelf(self, user1, user2):
        ujid1 = jid.internJID(user1).userhost()
        ujid2 = jid.internJID(user2).userhost()
        if ujid1 == ujid2:
            return True
        return False

    def checkAdmin(self, room, user):
        return self.parent.checkAdmin(room, user)

    def checkBanned(self, room, user):
        return self.parent.checkBanned(room, user)
        
    def _check_role(self, room, user, role):
        return self.parent._check_role(room, user, role)

    def checkModerator(self, room, user):
        return self.parent.checkModerator(room, user)

    def getAdmins(self, room, admin, host=None):
        """
        """
    
        def get_admins(r):
            if self.checkAdmin(r, admin):
                return r['admin']
            else:
                raise NotAllowed
        
        d = self.parent.storage.getRoom(room, host=host)
        d.addCallback(get_admins)
        return d

    def getOutcasts(self, room, admin, host=None):
        """
        """
    
        def get_a(r):
            if self.checkAdmin(r, admin):
                return r['outcast'], r['reason']
            else:
                raise NotAllowed
        
        d = self.parent.storage.getRoom(room, host=host)
        d.addCallback(get_a)
        return d

    def getMembers(self, room, admin, host=None):
        """
        """
    
        def get_a(r):
            if self.checkAdmin(r, admin):
                return r['member']
            else:
                raise NotAllowed
        
        d = self.parent.storage.getRoom(room, host=host)
        d.addCallback(get_a)
        return d

    def getRoles(self, room, role, admin, host=None):
        """
        """
    
        def get_a(r):
            if self.checkAdmin(r, admin):
                roles = []
                for u in r['roster'].values():
                    if u['role'] == role:
                        roles.append(u)
                return roles
            else:
                raise NotAllowed
        
        d = self.parent.storage.getRoom(room, host=host)
        d.addCallback(get_a)
        return d


    
    def getMember(self, members, user, owner, host=None):
        return self.parent.getMember(members, user)
        
        
    def updateRoom(self, room, owner, **kwargs):
        def update(r):
            if self.checkOwner(r, owner):
                return self.parent.storage.updateRoom(room, **kwargs)
            else:
                raise NotAllowed
        d = self.parent.storage.getRoom(room, host=kwargs['host'])
        d.addCallback(update)
        return d
    
    def grantOwner(self, user, room, owner, host=None):
        """
        """
        def get_owner(r, user):
            if self.checkOwner(r, owner):
                if self.checkSelf(user, owner):
                    raise NotAllowed
                try:
                    jid_user = jid.internJID(user).userhost()
                except:
                    jid_user = ''   
                mjid = None
                cjid = None
                dlist = []
                for m in r['roster'].values():
                    # TODO - get rid of jid stuff, this can not be jabber specific
                    mjid = m['jid']
                    if jid.internJID(mjid).userhost().lower() == jid_user.lower() or \
                           m['nick'].lower() == user.lower():
                        cjid = mjid.lower()
                        if m['nick'].lower() == user.lower():
                            user = mjid
                            
                        r['roster'][cjid]['role'] = 'moderator'
                        r['roster'][cjid]['affiliation'] = 'owner'
                        break
                if user not in r['owner']:
                    # set in storage
                    do = self.parent.storage.setOwner(room, user, host=host)
                    
                    dlist.append(do)
                if cjid:
                    # set in roster
                    dr = self.parent.storage.setRole(room, user, 'moderator', host=host)
                    dlist.append(dr)
                    
                                    
                dl = defer.DeferredList(dlist)
                dl.addErrback(lambda x: self.error(NotAllowed, x)) 
                dl.addCallback(lambda _: r['roster'])
                return dl
                
            else:
                raise NotAllowed
        
        d = self.parent.storage.getRoom(room, host = host)
        d.addCallback(get_owner, user)
        d.addErrback(lambda x: self.error(NotAllowed, x)) # this should be something else 
        #d.addErrback(lambda x: log.err(x))
        return d

    def grantPlayer(self, user, room, owner, host=None):
        """
        """
        def set_player(r, user):
            
            if self.checkOwner(r, owner):
                
                mjid = None
                cjid = None
                try:
                    jid_user = jid.internJID(user).userhost()
                except:
                    jid_user = ''   
                
                for m in r['roster'].values():
                    # TODO - get rid of jid stuff, this can not be jabber specific
                    mjid = m['jid']
                    if jid.internJID(mjid).userhost().lower() == jid_user.lower() or \
                           m['nick'].lower() == user.lower():
                        cjid = mjid.lower()
                        if m['nick'].lower() == user.lower():
                            user = m['jid']
                        r['roster'][cjid]['role'] = 'player'
                        r['roster'][cjid]['affiliation'] = 'player'
                        break
                dlist = []   
                if cjid:
                    
                    dr = self.parent.storage.setRole(room, user, 'player', host=host)
                    dlist.append(dr)
                d = self.parent.storage.setAffiliation(room, user, 'player', host=host)
                    
                dlist.append(d)
                dl = defer.DeferredList(dlist)
                dl.addCallback(lambda _: r['roster'])
                dl.addErrback(lambda x:self.error(NotAllowed,x))
                return dl
                
            else:
                raise NotAllowed
        
        d = self.parent.storage.getRoom(room, host=host)
        d.addCallback(set_player, user)
        d.addErrback(lambda x: self.error(NotAllowed, x)) 
        #d.addErrback(lambda x: log.err(x)) 
        return d    

    def grantAdmin(self, user, room, owner, host=None):
        """
        """

        def set_admin(r, user):
            if self.checkOwner(r, owner):
                mjid = None
                cjid = None
                dlist = []
                
                if self.checkSelf(user, owner):
                    raise NotAllowed
                try:
                    jid_user = jid.internJID(user).userhost().lower()
                except:
                    jid_user = ''
                user_check = user.lower()

                for m in r['roster'].values():
                    mjid = m['jid']
                    nick_check = m['nick'].lower()
                    if jid.internJID(mjid).userhost().lower() == jid_user or \
                           nick_check == user_check:
                        cjid = mjid.lower()
                        if nick_check == user_check:
                            user = m['jid']
                        r['roster'][cjid]['role'] = 'moderator'
                        r['roster'][cjid]['affiliation'] = 'admin'
                        break
                if cjid:
                    dsr = self.parent.storage.setRole(room, user, 'moderator', host=host)
                    dlist.append(dsr)
                    
                dsa = self.parent.storage.setAffiliation(room, user, 'admin', host=host)
                dlist.append(dsa)
                
                d = defer.DeferredList(dlist)
                d.addCallback(lambda _: r['roster'])
                d.addErrback(lambda x:self.error(NotAllowed,x))
                #d.addErrback(lambda x: log.err(x))
                return d
                
            else:
                raise NotAllowed
        
        d = self.parent.storage.getRoom(room, host=host)
        d.addCallback(set_admin, user)
        #d.addErrback(lambda x:self.error(NotAllowed, x)) 
        d.addErrback(lambda x: log.err(x))
        return d


    def revokeOwner(self, user, room, owner, host=None):
        """
        """
        def del_owner(r):
            if self.checkOwner(r, owner):
                
                if self.checkSelf(user, owner):
                    raise NotAllowed
                if user.find('@') == -1:
                    for m in r['roster'].values():
                        if m['nick'] == user:
                            user = jid.internJID(m['jid']).userhost()
                            break
                if user not in r['owner']:
                    del r['owner'][user]
                return r['roster']
            else:
                raise NotAllowed
        d = self.parent.storage.getRoom(room, host = host)
        d.addCallback(del_owner)
        return d

    def getOwner(self, room, user, owner, host=None):
        """
        """
        def get_owner(r):
            if self.checkOwner(r, owner):
                if user.find('@') == -1:
                    for m in r['roster'].values():
                        if m['nick'] == user:
                            user = jid.internJID(m['jid']).userhost()
                            break
                if user in r['owner']:
                    return r['owner'][user]
                        
                return
            else:
                raise NotAllowed
        d = self.parent.storage.getRoom(room, host=host)
        d.addCallback(get_owner)
        d.addErrback(lambda x: self.error(NotAllowed, x)) 
        return d

    def checkOwner(self, room, owner):
        return self.parent.checkOwner(room, owner)

    def getOwners(self, room, owner, host=None):
        """
        """
        def get_owners(r):
            if self.checkOwner(r, owner):
                return r['owner']
            else:
                raise NotAllowed

        d = self.parent.storage.getRoom(room, host=host)
        d.addCallback(get_owners)
        return d


    def invite(self, room, to, frm, host=None):
        def admin_inv(r, ret_room):
            # need to make a member
            return ret_room
        
        def inv(r):
            if not r:
                raise RoomNotFound
            # if invite is allowed
            if r.has_key('invites') and not r['invites']:
                log.msg('Room does not allow for invites')
                raise NotAllowed
            
            # if room is invite only then check for correct privs
            if r.has_key('invitation') and r['invitation']:
                
                d = self.grantMembership(to, room, frm, host=host)
                d.addCallback(admin_inv, r)
                return d
            else:
                return r
           
        # grab room
        d = self.parent.getRoom(room, host=host)
        d.addCallback(inv)
        return d
