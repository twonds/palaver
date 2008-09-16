# Copyright (c) 2005 - 2007 Christopher Zorn, OGG, LLC 
# See LICENSE.txt for details


import string, time
from twisted.enterprise import adbapi
from twisted.python import log, failure
from twisted.internet import defer
from twisted.words.protocols.jabber import jid
from zope.interface import implements
import cPickle as pickle
import groupchat
import storage

from pysqlite2 import dbapi2 as sqlite

AFFILIATION_LIST = ['admin','member','owner','player','outcast']        


class Room(dict):
    pass

def jid_userhost(user):
    return str(user).split("/", 1)[0]

def jid_user(user):
    return str(user).split("@")[0]
    
def jid_resource(user):
    try:
        return str(user).split("/", 1)[1]
    except:
        pass
    
MAP_DICT = {
    0  :  "id",
    1  :  "name",
    2  :  "roomname",
    3  :  "subject",
    4  :  "subject_change",
    5  :  "persistent",
    6  :  "moderated",
    7  :  "private",
    8  :  "history",
    9  :  "game",
    10 :  "invitation",
    11 :  "invites",
    12 :  "hidden",
    13 :  "locked",
    14 :  "subjectlocked",
    15 :  "description",
    16 :  "leave",
    17 :  "join",
    18 :  "rename",
    19 :  "maxusers",
    20 :  "privmsg",
    21 :  "change_nick",
    22 :  "query_occupants",
    23 :  "hostname",
    }

# Connection and Cursor classes derived from Axiom 
# http://divmod.org/trac/browser/trunk/Axiom/axiom/_pysqlite2.py?rev=13432

class Cursor(object):
    def __init__(self, connection, timeout):
        self._connection = connection
        self._cursor     = connection.conn.cursor()
        self.timeout     = timeout
 	 	
    def __iter__(self):
        return iter(self._cursor)
 	
 	
    def rowcount(self):
        return self._cursor.rowcount

    def time(self):
        """
        Return the current wallclock time as a float representing seconds
        from an fixed but arbitrary point.
        """
        return time.time()
 	
 	
    def sleep(self, seconds):
        """
        Block for the given number of seconds.
 	
        @type seconds: C{float}
        """
        time.sleep(seconds)
 	
	
    def execute(self, sql, args=()):
        try:
            try:
                blockedTime = 0.0
                t = self.time()
                try:
                    # SQLite3 uses something like exponential backoff when
                    # trying to acquire a database lock.  This means that even
                    # for very long timeouts, it may only attempt to acquire
                    # the lock a handful of times.  Another process which is
                    # executing frequent, short-lived transactions may acquire
                    # and release the lock many times between any two attempts
                    # by this one to acquire it.  If this process gets unlucky
                    # just a few times, this execute may fail to acquire the
                    # lock within the specified timeout.
                    
                    # Since attempting to acquire the lock is a fairly cheap
                    # operation, we take another route.  SQLite3 is always told
                    # to use a timeout of 0 - ie, acquire it on the first try
                    # or fail instantly.  We will keep doing this, ten times a
                    # second, until the actual timeout expires.
 	
                    # What would be really fantastic is a notification
                    # mechanism for information about the state of the lock
                    # changing.  Of course this clearly insane, no one has ever
                    # managed to invent a tool for communicating one bit of
                    # information between multiple processes.
                    while 1:
                        try:
                            return self._cursor.execute(sql, args)                           
                        except sqlite.OperationalError, e:
                            if e.args[0] == 'database is locked':
                                now = self.time()
                                if self.timeout is not None:
                                    if (now - t) > self.timeout:
                                        raise Exception, 'Timeout Error', e
                                    self.sleep(0.1)
                                    blockedTime = self.time() - t
                            else:
                                raise
                finally:
                    txntime = self.time() - t
                    if txntime - blockedTime > 2.0:
                        log.msg('Extremely long execute: %s' % (txntime - blockedTime,))
                        log.msg(sql)
                        
            except sqlite.OperationalError, e:
                if e.args[0] == 'database schema has changed':
                    return self._cursor.execute(sql, args)
                raise
        except (sqlite.ProgrammingError,
                sqlite.InterfaceError,
                sqlite.OperationalError), e:
            raise e
        
            
    def lastRowID(self):
        return self._cursor.lastrowid
    
    def fetchall(self):
        return self._cursor.fetchall()

    def fetchone(self):
        return self._cursor.fetchone()

    def close(self):
        self._cursor.close()

class SqliteConnection:
    """
    an attempt at an sqlite connection class
    """

    def __init__(self, database):
        self.database = database
        self.conn = sqlite.connect(database,isolation_level=None)
        self._timeout = 0

    def cursor(self):
        return Cursor(self, self._timeout)
 	
 	
    def close(self):
        # cur.close()
        self.conn.close()

    def runWithConnection(self, func, *args, **kwargs):
        """
        run with connection replacement
        """
        
        # conn = sqlite.connection(self.database)
        try:
            return defer.succeed(func(self, *args, **kwargs))
        except:
            log.err()
            return defer.fail()



class Storage:

    implements(storage.IStorage)
    sadmins = []
    users = {}
    
    def __init__(self, database):
        """
        create a sqlite storage mechanism
        datbase - filename or :memory: for memory db
        """
        
        self._dbpool = SqliteConnection(database)
        

    def _fetch_user(self, conn, user):
        if not user:
            log.msg('No user to fetch?')
            return
        cursor = conn.cursor()
        resource = jid_resource(user)
        FETCH_SQL = """SELECT id, username, presence, resource 
                       FROM muc_users WHERE LOWER(username) = LOWER(?) """ 
        cursor.execute(FETCH_SQL, (user,))
        dbuser = cursor.fetchone()
        
        return dbuser

    def _fetch_users(self, conn, user):
        if not user:
            log.msg('No user to fetch?')
            return
        cursor = conn.cursor()
        resource = jid_resource(user)
        username = jid_userhost(user)

        cursor.execute("SELECT id, username, presence, resource FROM muc_users WHERE username ILIKE '"+username+"%'")
        dbusers = cursor.fetchall()
        
        return dbusers

    def _create_user(self, conn, user):
        cursor = conn.cursor()
        resource = jid_resource(user)

        dbuser = self._fetch_user(conn, user)
        # TODO - add other values
        
        if not dbuser and self.users.has_key(user):
            dbuser = self.users[user]
        
        if not dbuser:
            try:    
                cursor.execute("""INSERT OR REPLACE INTO muc_users (username, resource)
            VALUES (?, ?)
            """ , (user, resource))
            except:
                log.err()
                pass
                

            dbuser = self._fetch_user(conn, user)

            self.users[user] = dbuser
        elif self.users.has_key(user):
            del self.users[user]
        
        return dbuser


    def _update_user(self, conn, user):
        cursor = conn.cursor()
        resource = jid_resource(user)

        dbuser = self._fetch_user(conn, user)
        
        if dbuser:
            try:        
                cursor.execute("""UPDATE muc_users SET resource = ? WHERE id = ?)
            """ , (resource, dbuser[0]))
            except:
                log.err()
                            
        return dbuser

    def _add_roster(self, conn, dbroom, dbuser, nick, status = '', show = '', legacy=True, host = None, affiliation='none', role='none'):        
        cursor = conn.cursor()
        
        if not dbuser:
            raise Exception, 'User can not be added to the roster.'

        cursor.execute("""INSERT INTO muc_rooms_roster 
                          (user_id, room_id, nick, status, show, legacy, affiliation, role)
                          VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (int(dbuser[0]), int(dbroom[0]), nick, status, show, legacy, affiliation, role))
        
        
        

    def _in_roster(self, conn, room_id, user_id, host):
        cursor = conn.cursor()
        
        cursor.execute("""SELECT 1 FROM muc_rooms_roster, muc_rooms, muc_users
                          WHERE muc_rooms_roster.user_id = muc_users.id
                          AND   muc_rooms.id = ?
                          AND   muc_users.id = ?
                          AND   muc_rooms.hostname = ?
                          AND   muc_rooms_roster.room_id = muc_rooms.id
            """ , (room_id ,user_id, host))
        ul = cursor.fetchone()
        
        if ul:
            return True
        return False

    def _fetch_in_roster(self, conn, room, user, host):
        cursor = conn.cursor()
        cursor.execute("""SELECT muc_users.id, muc_rooms.id FROM muc_rooms_roster, muc_rooms, muc_users
                          WHERE muc_rooms_roster.user_id = muc_users.id
                          AND   LOWER(muc_rooms.name) = LOWER(?)
                          AND   LOWER(muc_users.username) = LOWER(?)
                          AND   muc_rooms.hostname = ?
                          AND   muc_rooms_roster.room_id = muc_rooms.id
            """ , (room , user, host))
        ul = cursor.fetchone()
        
        if not ul:
            ul = []
        return ul

            
    def _fetch_room(self, conn, room, host):
        cursor = conn.cursor()
        try:
            if type(room) == type(''):
                room = unicode(room, 'utf-8')

            val_str = string.join([' "%s"' % (val,) for key, val in MAP_DICT.iteritems()], ", ")            
            FETCH_SQL = """SELECT %s FROM muc_rooms WHERE LOWER(name) = LOWER(?) AND hostname = ?""" % (val_str,)
            cursor.execute(FETCH_SQL , (room, host))        
            r = cursor.fetchone()
            
        except:
            log.err()
            r = None
            
        return r
    
    def _fetch_roster(self, conn, room_id, host = None):
        cursor = conn.cursor()
        cursor.execute("""SELECT muc_users.id,
                                 muc_users.username,
                                 muc_users.presence,
                                 muc_users.resource,
                                 muc_rooms_roster.id,
                                 muc_rooms_roster.room_id,
                                 muc_rooms_roster.user_id,
                                 muc_rooms_roster.role,
                                 muc_rooms_roster.nick,
                                 muc_rooms_roster.show,
                                 muc_rooms_roster.status,
                                 muc_rooms_roster.legacy,
                                 muc_rooms_roster.affiliation
                          FROM muc_users, muc_rooms_roster
                          WHERE muc_rooms_roster.room_id = ?
                          AND muc_rooms_roster.room_id = ?
                          AND muc_rooms_roster.user_id = muc_users.id
        """ , (room_id, room_id))        
        roster = cursor.fetchall()
                    
        return roster
    
    def _fetch_attribute(self, conn, room_id, attr, host = None):
        pval = None
        cursor = conn.cursor()
        cursor.execute("""SELECT value FROM muc_roomattributess
                          WHERE muc_roomattributess.room_id = ?
                          AND muc_roomattributess.key = ?
        """ , (room_id, attr))        
        row = cursor.fetchone()
        if row:
            pval = row[0]
                    
        return pval
        

    def _fetch_owners(self, conn, room_id, host = None):
        cursor = conn.cursor()
        cursor.execute("""SELECT
                          muc_users.id,
                          muc_users.username,
                          muc_users.presence,
                          muc_users.resource,
                          muc_rooms_owners.id,
                          muc_rooms_owners.room_id,
                          muc_rooms_owners.user_id
                         
                          FROM muc_users, muc_rooms_owners
                          WHERE muc_rooms_owners.room_id = ?
                          AND muc_rooms_owners.user_id = muc_users.id
        """ , (room_id, ))        
        dbowners = cursor.fetchall()
        
        return dbowners
    
    def _fetch_outcasts(self, conn, room_id, host = None):
        cursor = conn.cursor()
        cursor.execute("""SELECT
                          muc_users.id,
                          muc_users.username,
                          muc_users.presence,
                          muc_users.resource,
                          muc_rooms_outcasts.id,
                          muc_rooms_outcasts.room_id,
                          muc_rooms_outcasts.user_id,
                          muc_rooms_outcasts.reason
                          FROM muc_users, muc_rooms_outcasts
                          WHERE muc_rooms_outcasts.room_id = ?
                          AND muc_rooms_outcasts.user_id = muc_users.id
        """ , (room_id, ))
        outcasts = cursor.fetchall()
        
        return outcasts

    def _fetch_admins(self, conn, room_id, host = None):
        cursor = conn.cursor()
        cursor.execute("""SELECT
                          muc_users.id,
                          muc_users.username,
                          muc_users.presence,
                          muc_users.resource,
                          muc_rooms_admins.id,
                          muc_rooms_admins.room_id,
                          muc_rooms_admins.user_id
                          FROM muc_users, muc_rooms_admins
                          WHERE muc_rooms_admins.room_id = ?
                          AND muc_rooms_admins.user_id = muc_users.id
        """ , (room_id, ))
        a = cursor.fetchall()
        
        return a
        
    
    def _fetch_members(self, conn, room_id, host = None):
        cursor = conn.cursor()
        cursor.execute("""SELECT
                          muc_users.id,
                          muc_users.username,
                          muc_users.presence,
                          muc_users.resource,
                          muc_rooms_members.id,
                          muc_rooms_members.room_id,
                          muc_rooms_members.user_id
                          FROM muc_users, muc_rooms_members
                          WHERE muc_rooms_members.room_id = ?
                          AND muc_rooms_members.user_id = muc_users.id
        """ , (room_id, ))
        a = cursor.fetchall()
        
        return a
    
    def _fetch_players(self, conn, room_id, host = None):
        cursor = conn.cursor()
        cursor.execute("""SELECT
                          muc_users.id,
                          muc_users.username,
                          muc_users.presence,
                          muc_users.resource,
                          muc_rooms_players.id,
                          muc_rooms_players.room_id,
                          muc_rooms_players.user_id
                          FROM muc_users, muc_rooms_players
                          WHERE muc_rooms_players.room_id = ?
                          
                          AND muc_rooms_players.user_id = muc_users.id
        """ , (room_id, ))
        a = cursor.fetchall()
        
        return a



    def _clear_owners(self, conn, room_id):
        cursor = conn.cursor()
        cursor.execute("""DELETE FROM muc_rooms_owners
                          WHERE muc_rooms_owners.room_id = ?
                          
        """ , (room_id,))
        
        return True

    def _clear_outcasts(self, conn, room_id):
        cursor = conn.cursor()
        cursor.execute("""DELETE FROM muc_rooms_outcasts
                          WHERE muc_rooms_outcasts.room_id = ?
                          
        """ , (room_id,))
        

        return True

    def _clear_admins(self, conn, room_id):
        cursor = conn.cursor()
        cursor.execute("""DELETE FROM muc_rooms_admins
                          WHERE muc_rooms_admins.room_id = ?
                         
        """ , (room_id,))
        
        return True
    
    def _clear_members(self, conn, room_id):
        cursor = conn.cursor()
        cursor.execute("""DELETE FROM muc_rooms_members
                          WHERE muc_rooms_members.room_id = ?
                       
        """ , (room_id,))
        
        return True
    
    def _clear_players(self, conn, room_id):
        cursor = conn.cursor()
        cursor.execute("""DELETE FROM muc_rooms_players
                          WHERE muc_rooms_players.room_id = ?
                          """ , (room_id,))
        
        return True

    def _delete_owner(self, conn, room_id, user_id):
        cursor = conn.cursor()
        cursor.execute("""DELETE FROM muc_rooms_owners
                          WHERE muc_rooms_owners.room_id = ?
                          AND muc_rooms_owners.user_id = ?
        """ , (room_id, user_id))
        
        return True

    def _delete_outcast(self, conn, room_id, user_id):
        cursor = conn.cursor()
        cursor.execute("""DELETE FROM muc_rooms_outcasts
                          WHERE muc_rooms_outcasts.room_id = ?
                          AND muc_rooms_outcasts.user_id = ?
        """ , (room_id, user_id))
        
        return True

    def _delete_admin(self, conn, room_id, user_id):
        cursor = conn.cursor()
        cursor.execute("""DELETE FROM muc_rooms_admins
                          WHERE muc_rooms_admins.room_id = ?
                          AND muc_rooms_admins.user_id = ?
        """ , (room_id, user_id))
        
        return True
    
    def _delete_member(self, conn, room_id, user_id):
        cursor = conn.cursor()
        cursor.execute("""DELETE FROM muc_rooms_members
                          WHERE muc_rooms_members.room_id = ?
                          AND muc_rooms_members.user_id = ?
        """ , (room_id, user_id))
        
        return True
    
    def _delete_player(self, conn, room_id, user_id):
        cursor = conn.cursor()
        cursor.execute("""DELETE FROM muc_rooms_players
                          WHERE muc_rooms_players.room_id = ?
                          AND muc_rooms_players.user_id = ?
        """ , (room_id, user_id))
        
        return True    

    def _update_role(self, conn, dbroom, dbuser, role):
        cursor = conn.cursor()
        cursor.execute("""UPDATE muc_rooms_roster SET role = ?
        WHERE user_id = ? AND room_id = ?""" ,
                       (role, int(dbuser), int(dbroom)))

    def _update_affiliation(self, conn, dbroom, dbuser, a):
        updated = False
        cursor = conn.cursor()
        try:
            cursor.execute("""UPDATE muc_rooms_roster SET affiliation = ?
        WHERE user_id = ? AND room_id = ?""" ,
                           (a, int(dbuser), int(dbroom)))
            updated = True
        except:
            pass
        return updated

    def _check_nick(self, conn, room_id, user, nick):
        cursor = conn.cursor()
        cursor.execute("""SELECT nick FROM muc_rooms_roster
                          WHERE nick ILIKE ?
                          AND room = ?""" , (nick, room_id))
        # we should use rowcount?

        if not cursor.fetchone() is None:
            return True
        return False

    def _change_status(self, conn, dbroom, dbuser, show = '', status = '', legacy = False, host = None):        
        cursor = conn.cursor()
        cursor.execute("""UPDATE muc_rooms_roster SET show = ? , status = ? , legacy = ?
        WHERE user_id = ? AND room_id = ? 
        """ , (show, status, legacy, str(dbuser), str(dbroom)))
        
        return True
    
    def _create_room(self, conn, room, owner, new_room):
        cursor = conn.cursor()
        
        INSERT_SQL = """INSERT INTO muc_rooms (id, name, roomname, subject, persistent,
 	                                     moderated, private,
	                                     game, hidden, locked,
                                             hostname, change_nick,
                                             invites, privmsg
                                             )
                          VALUES (NULL, ?, ?, ?, 
                                  ?, ?, ?, 
                                  ?, ?, ?, 
                                  ?, ?, ?, ?)"""
        cursor.execute(INSERT_SQL, (room, room,
                                    new_room['subject'], new_room['persistent'],
                                    new_room['moderated'], new_room['private'],
                                    new_room['game'], new_room['hidden'],
                                    new_room['locked'], new_room['host'],True,
                                    new_room['invites'], new_room['privmsg'], ))
        dbroom_id = cursor.lastRowID()


        return dbroom_id


    @defer.inlineCallbacks
    def _createRoom(self, d, room, owner, **kwargs):
        """
        Create the user and room, then insert user into owners
        """

        # NOTE - we should already know the room does not exist
        new_room = {
            'name': room,
            'subject': '',
            'persistent': False,
            'moderated': False,
            'private': True,
            'game': False,
            'hidden': False,
            'locked': True,
            'invites': True,
            'privmsg': True,
            }
        new_room.update(kwargs)

        if self._checkBool(kwargs['legacy']):
            new_room['locked'] = False


        dbroom_id = yield self._dbpool.runWithConnection(self._create_room, room, owner, new_room)
        new_room['id'] = dbroom_id
        dbuser = None
        if not dbuser:    
            dbuser = yield self._dbpool.runWithConnection(self._create_user, owner)


        if not dbuser:
            d.errback(failure.Failure(Exception, 'Owner can not be added'))                    
            return

        m = yield self._dbpool.runWithConnection(self._insert_affiliation, 'owner', dbroom_id, dbuser[0])

        d.callback(room)
        
    def createRoom(self, room, owner, **kwargs):
        d = defer.Deferred()
        self._createRoom(d, room, owner, **kwargs)
        return d


    def _fetchInRoster(self, room, user, host):
        return self._dbpool.runWithConnection(self._fetch_in_roster, room, user, host)

    
    @defer.inlineCallbacks
    def _setRole(self, d, room, user, role, host):
        
        ur = yield self._fetchInRoster(room, user, host)
        if ur:
            dbuser, dbroom = ur
            u = yield self._dbpool.runWithConnection(self._update_role, dbroom, dbuser, role)
            d.callback(True)
        else:
            d.callback(False)
    

    
    def setRole(self, room, user, role, host = None):
        """
        Set the role of the user in the room
        """
        d = defer.Deferred()
        self._setRole(d, room, user, role, host)
        return d
    
    def _set_attribute(self, conn, dbroom, attr, value, host):
        cursor = conn.cursor()

        attr_val = self._fetch_attribute(conn, dbroom, attr, host)
        pval = pickle.dumps(value)

        if attr_val is not None:
            cursor.execute("""UPDATE muc_roomattributess SET value = ? WHERE key = ? AND room_id = ? """ , (pval, attr, dbroom))
        else:        
            cursor.execute("""INSERT OR REPLACE INTO muc_roomattributess (room_id, key, value) VALUES (?, ?, ?)""" , (dbroom, attr, pval))

        return pval

    @defer.inlineCallbacks
    def _setAffiliation(self, d, room, user, affiliation, reason, host):
        if not host:
            d.errback(failure.Failure(Exception, 'Host is None'))
        
        dbuser = None
        dbroom = None
        if affiliation != 'none' and affiliation not in AFFILIATION_LIST:
            raise Exception, 'Not a valid affilation'
        else:    
            dbroom = yield self._fetchRoom(room, host)
        # switch through affliation

        if not dbroom:
            raise Exception, 'Room Not Found'
        dbuser = yield self._fetchUser(user)
        
        if not dbuser:
            dbuser = yield self._dbpool.runWithConnection(self._create_user, user)
                
        if not dbuser:
            raise Exception, 'User Not Found'

        # check for resource 
        resource = jid_resource(user)
        username = jid_userhost(user)
        users = []
        user_check = []
        

        if user.lower() not in user_check or username.lower() not in user_check:
            users = [dbuser]
            noresource = yield self._fetchUser(username)
            if noresource:
                users = [dbuser, noresource]

        for u in users:
            for a in AFFILIATION_LIST:
                fnc = getattr(self,'_delete_'+a, None)            
                if fnc:
                    try:
                        df = yield self._dbpool.runWithConnection(fnc, dbroom[0], u[0])
                    except:
                        log.err()
                        log.msg('Error in removing affiliation %s %s' , (str(dbroom), str(dbuser),))
            
        if host and dbroom and dbuser:    
            if affiliation != 'none':
                try:
                    i = yield self._dbpool.runWithConnection(self._insert_affiliation,
                                                             affiliation,
                                                             dbroom[0],
                                                             dbuser[0],
                                                             reason)
                except:
                    log.err()
                    log.msg('Error in inserting affiliation %s %s %s' % (affiliation, str(dbroom), str(dbuser)))
            else:
                log.msg('Affiliation is none %s' , (user,))
        else:
            log.msg('We did not remove the affiliation %s %s %s' % (str(host), str(dbroom), str(u),))
        # update roster
        u = yield self._dbpool.runWithConnection(self._update_affiliation, dbroom[0], dbuser[0], affiliation)

        d.callback(True)


            
            
    def _insert_affiliation(self, conn, affiliation, dbroom, dbuser, reason = None):
        cursor = conn.cursor()
        
        if affiliation == 'outcast' and reason:
            INSERT_SQL = """INSERT INTO muc_rooms_%s
                                 (user_id, room_id, reason)
                          VALUES (?, ?, ?)""" % (affiliation+'s',) 
            args = (dbuser, dbroom, reason.__str__(), )

        else:
            INSERT_SQL = """INSERT INTO muc_rooms_%s
                                 (user_id, room_id)
                          VALUES (?, ?)""" % (affiliation+'s',)
            args = (dbuser, dbroom,)

        try:
            cursor.execute(INSERT_SQL, args)
        except:
            log.err()
            return False
        return True

    def setAffiliation(self, room, user, affiliation, reason = '', host = ''):
        """
        Set the affiliation of a user for a room.
        """
        
        d = defer.Deferred()
        try:
            self._setAffiliation(d, room, user, affiliation, reason, host)
        except Exception, e:
            
            d.errback(e)
            
        return d
        
        
    def _get_role(self, conn, room, user, host = None):
        role = None
        cursor = conn.cursor()

        cursor.execute("""SELECT muc_rooms_roster.role
                          FROM muc_rooms, muc_rooms_roster, muc_users
                          WHERE LOWER(muc_rooms.name) = LOWER(?) AND
                                LOWER(muc_users.username) = LOWER(?) AND
                                muc_rooms.id = muc_rooms_roster.room_id AND
                                muc_users.id = muc_rooms_roster.user_id AND
                                muc_rooms.hostname = ?""" , (room, user, host))

        
        res = cursor.fetchone()
        if res:
            role = res[0]
        return role
            
        
    def getRole(self, room, user, host = None):
        return self._dbpool.runWithConnection(self._get_role, room, user, host)

    @defer.inlineCallbacks
    def _getAffiliation(self, d, room, user, host):
        affiliation = None

        dbroom = yield self._fetchRoom(room, host)
        resource = jid_resource(user)
        if dbroom is None:
            log.msg('Room not found ', room)
            d.errback(failure.Failure(Exception, 'Room not found'))
            return

        for a in AFFILIATION_LIST:
            a_list = yield self._fetchAffiliations(dbroom[0], a)
            if a == 'admin':
                a_list += self.sadmins

            for u in a_list:
                if u[1].lower() == user.lower():
                    affiliation = a
                    break
                elif jid_userhost(u[1]).lower() == jid_userhost(user).lower():
                    affiliation = a
                    break
                    
        d.callback(affiliation)

    
    def getAffiliation(self, room, user, host = None):
        """
        Grab the affiliation of the member
        """
        d = defer.Deferred()
        self._getAffiliation(d, room, user, host)
        return d


    def _in_room(self, conn, room, user, nick, host):
        cursor = conn.cursor()
        # check if user is already in the room
                
        cursor.execute("""SELECT DISTINCT 1 FROM muc_rooms_roster, muc_rooms, muc_users
        WHERE muc_rooms_roster.room_id = muc_rooms.id AND LOWER(muc_rooms.name) = LOWER(?)
        AND muc_rooms_roster.user_id = muc_users.id
        AND LOWER(muc_users.username) = LOWER(?)
        AND muc_rooms_roster.nick = ?
        AND muc_rooms.hostname = ?
        """ , (room, user, nick, host))

        ul = cursor.fetchone()
        return ul

    def _inRoom(self, room, user, nick, host):
        return self._dbpool.runWithConnection(self._in_room, room, user, nick, host)
    
    @defer.inlineCallbacks
    def _joinRoom(self, d, room, user, nick, status = '', show = '', legacy= True, host = None):

        ul = yield self._inRoom(room, user, nick, host)
        
        if not ul:
            # add user to the roster and user
            dbuser = yield self._fetchUser(user)
            if not dbuser:
                dbuser = yield self._dbpool.runWithConnection(self._create_user, user)

            dbroom = yield self._fetchRoom(room, host)
            affiliation = yield self.getAffiliation(room, user, host)

            if affiliation:
                role = groupchat.AFFILIATION_ROLE_MAP[affiliation]
            elif dbroom[6]:
                role = 'visitor'
            else:
                role = 'participant'
            try:
                a = yield self._dbpool.runWithConnection(self._add_roster,
                                                         dbroom, dbuser,
                                                         nick, status,
                                                         show, legacy, host,
                                                         affiliation=affiliation,
                                                         role=role)                    
            except:
                log.msg('Can not add to roster %s %s %s'  % (room, user, nick, ))
                # d.errback(failure.Failure(Exception, 'Can not join roster twice'))
                d.callback(False)
                return
            
        d.callback(True)
            
    def joinRoom(self, room, user, nick, status = None, show = None, legacy = True, host = ''):
        """
        Join a room
        """
        d = defer.Deferred()
        self._joinRoom(d, room, user, nick,
                       status=status,
                       show=show,
                       legacy=legacy,
                       host=host)
        return d

    def setNewRole(self, room, user, host = ''):
        """ Set a new role for a user in a room """
        d = defer.Deferred()
        try:
            self._setNewRole(d, room, user, host = host)
        except Exception, e:
            d.errback(e)
        return d 
    
    @defer.inlineCallbacks
    def _setNewRole(self, d, room, user, host = ''):
        
        dbroom = yield self._fetchRoom(room, host)

        dbuser = yield self._fetchUser(user)
        if dbuser == None:
            raise Exception, 'User not found %s' % (user,)

        affiliation = yield self.getAffiliation(room, user, host)

        role = 'participant'
        if affiliation and affiliation == 'admin':
            role = 'moderator'            
        elif affiliation and affiliation == 'member':
            role = 'participant'
        elif affiliation and affiliation == 'player':
            role = 'player'
        elif affiliation and affiliation == 'owner':
            role = 'owner'
        elif affiliation and affiliation == 'outcast':
            role = 'outcast'
        elif affiliation and dbroom[6]:
            role = 'visitor'
                
        u = yield self._dbpool.runWithConnection(self._update_role, dbroom[0], dbuser[0], role)
        
        d.callback(role)
    
    
    
    @defer.inlineCallbacks
    def _changeStatus(self, d, room, user, show = None, status = None, legacy = False, host = None):

        ur = yield self._fetchInRoster(room, user, host)

        if ur:
            dbuser, dbroom = ur
            s = yield self._dbpool.runWithConnection(self._change_status,
                                                     dbroom,
                                                     dbuser,
                                                     show,
                                                     status,
                                                     legacy,
                                                     host)
            d.callback(s)
        else:
            d.errback(failure.Failure(Exception, 'Room Not Found'))
            
    def changeStatus(self, room, user, show = None, status = None, legacy = False, host = None):
        """
        Change the presence of a user in a room.
        """
        d = defer.Deferred()
        self._changeStatus(d, room, user, show, status, legacy, host)
        return d
        
    
    def _part_room(self, conn, dbroom, dbuser):
        cursor = conn.cursor()
        try:
            cursor.execute("""DELETE FROM muc_rooms_roster 
            WHERE user_id = ? AND room_id = ?
            """, (int(dbuser), int(dbroom)))
        except:
            log.err()
            return False
        return True

    @defer.inlineCallbacks
    def _partRoom(self, d, room, user, nick, host):
        # check for room types, grab role and affiliation
        dbroom = yield self._fetchRoom(room, host)
            
        dbuser = yield self._fetchUser(user)

        if dbuser and dbroom:
            roster = yield self._fetchRoster(dbroom[0])
            u = {}
            u['role'] = 'none'
            u['affiliation'] = 'none'
            
            for m in roster:
                if m[1].lower() == user.lower(): 
                    # TODO - create a better way to map these
                    
                    u['jid'] = m[1] 
                    u['nick'] = m[8]
                    u['role'] = 'none'
                    u['affiliation'] = 'none'
            p = yield self._dbpool.runWithConnection(self._part_room, dbroom[0], dbuser[0])
            if p:
                d.callback(u)
            else:
                log.msg('Did not leave the room')
                d.callback(None)
        else:
            log.msg('=================== no user or room to part ==========================')
            log.msg(room)
            log.msg(user)
            log.msg(nick)
            d.callback(None)

    def partRoom(self, room, user, nick, host = None):
        """
        The user leaves the room
        """
        d = defer.Deferred()
        self._partRoom(d, room, user, nick, host)
        return d


    def _delete_room(self, conn, room, owner = None, check_persistent = False, host = None):
        c = conn.cursor()
        if check_persistent:
            do_sql = True

            if do_sql:
                c.execute("""SELECT persistent FROM muc_rooms WHERE LOWER(name) = LOWER(?) AND hostname = ?""", (room, host))
                p = c.fetchone()
                if p and self._checkBool(p[0]):
                    # This means room is persistent and should not be deleted
                    return False
        # dbroom = self._fetch_room(c, room, host)

        c.execute("""DELETE FROM muc_rooms WHERE LOWER(name) = LOWER(?) AND hostname = ? """, (room, host))

        if c.rowcount() == 1:
            return True
        return False

    
    def _get_attributes(self, conn, dbroom):
        cursor = conn.cursor()
        # get attributes
        cursor.execute("SELECT key, value FROM muc_roomattributess WHERE room_id = ?""" , (dbroom, ))
        return cursor.fetchall()

    
        
    def _fetchUser(self, user):
        return self._dbpool.runWithConnection(self._fetch_user, user)

    def _fetchRoom(self, room, host):
        return self._dbpool.runWithConnection(self._fetch_room, room, host)
        
    def _fetchRoster(self, room_id):
        return self._dbpool.runWithConnection(self._fetch_roster, room_id)
        
    def _fetchRoomAttributes(self, room_id):
        """ Get Room attributes """
        d  = self._dbpool.runWithConnection(self._get_attributes, room_id)
        return d
                            
    def _filterAffiliationList(self, alist):
        users = {}
        new_list = []
        user_list = []
        for u in alist:
            username = jid_userhost(u[1])
            resource = jid_resource(u[1])
            if not users.has_key(username):
                users[username] = []
            if resource is None or resource == '':
                new_list.append(u)
                user_list.append(username)
            else:
                users[username].append(u)
        for uk in users.keys():
            if uk not in user_list:        
                new_list += users[uk]

        return new_list

    def _appendAffiliations(self, room_id, affiliations):
        val = []
        for m in affiliations:
            val.append(m[1])
        return val

    def _fetchAffiliations(self, room_id, affiliation):
        """
        Grab an affilition list from the db
        """
        fnc = getattr(self, '_fetch_'+affiliation+'s', None)
        d  = self._dbpool.runWithConnection(fnc, int(room_id))
        return d
        
    @defer.inlineCallbacks
    def _getRoom(self, d, room, host, frm = None):
        ret_val = None
        r = None
        
        r = yield self._fetchRoom(room, host)

        if r:
            # create a cleaner way to map these
            ret_val = self._dbroomToHash(r)
            
            attribs = yield self._fetchRoomAttributes(r[0])
            for key, val in attribs:
                try:
                    ret_val[key] = pickle.loads(str(val))
                except:
                    log.err()
                    pass

            roster = yield self._fetchRoster(int(r[0]))
            
            members = yield self._fetchAffiliations(int(r[0]), 'member')
            ret_val['member'] = self._appendAffiliations(r[0], members)
            admins = yield self._fetchAffiliations(int(r[0]), 'admin')
            ret_val['admin'] = self._appendAffiliations(r[0], admins)
            owners = yield self._fetchAffiliations(int(r[0]), 'owner')
            ret_val['owner'] = self._appendAffiliations(r[0], owners)
            players = yield self._fetchAffiliations(int(r[0]), 'player')
            ret_val['player'] = self._appendAffiliations(r[0], players)
            
            outcasts  = yield self._fetchAffiliations(int(r[0]), 'outcast')
            
            ret_val['outcast'] = []
            ret_val['reason'] = {}
    
            for m in outcasts:
                ret_val['outcast'].append(m[1])
                if len(m)>7:
                    ret_val['reason'][m[1]] = m[7]

        
            ret_val['roster'] = []
            
            ret_val = self._dbrosterToHash(ret_val, roster)

        d.callback(ret_val)

    def getRoom(self, room, host, frm=None):
        """ Grab a room from the backend """
        d = defer.Deferred()
        try:
            self._getRoom(d, room, host, frm = frm)
        except:
            d.callback(None)
        return d


    def _doGetRoomsList(self, host, frm):

        def doGetRooms(conn, host, frm):
            cursor = conn.cursor()
                        
            SELECT_SQL = "SELECT name, hostname, hidden FROM muc_rooms WHERE hostname = ? "
            
            cursor.execute(SELECT_SQL , (host,))
            results = cursor.fetchall()
            return results

        return self._dbpool.runWithConnection(doGetRooms, host, frm)

    @defer.inlineCallbacks
    def _getRooms(self, host, d, frm = None):
        ret_rooms = []
        rooms = yield self._doGetRoomsList(host, frm)

        for r in rooms:
            if not r[2]:
                dbroom = yield self._fetchRoom(r[0], r[1])
                dbroom = self._dbroomToHash(dbroom)
            else:
                dbroom = yield self.getRoom(r[0], r[1], frm=frm)
            ret_rooms.append(dbroom)
        d.callback(ret_rooms)

        
    def getRooms(self, host, frm = None):
        """ Get a list of all the rooms """    
        d = defer.Deferred()
        try:
            self._getRooms(host, d, frm = frm)
        except:
            d.errback()
            
        return d
        
    
    def setAdmin(self, room, user, host = None):
        return self.setAffiliation(room, user, 'admin', host = host)

    def setPlayer(self, room, user, host = None):
        return self.setAffiliation(room, user, 'player', host = host)

    def setOwner(self, room, user, host = None):
        return self.setAffiliation(room, user, 'owner', host = host)

    def setOutcast(self, room, user, reason=None, host = None):
        return self.setAffiliation(room, user, 'outcast', reason = reason, host = host)

    def setMember(self, room, user, host = None):
        return self.setAffiliation(room, user, 'member', host = host)

    def _get_room_members(self, conn, room, host, frm):
        
        r = self._fetch_room(conn, room, host)            
        dbmembers = self._fetch_members(conn, int(r[0]))
        members = []
        for m in dbmembers:
            members.append(m[1])
        return members
    
    def getRoomMembers(self, room, host = None, frm=None):
        return self._dbpool.runWithConnection(self._get_room_members, room, host, frm)
    

    def deleteRoom(self, room, owner = None, check_persistent = False, host = None):
        return self._dbpool.runWithConnection(self._delete_room, room, owner = owner, check_persistent = check_persistent, host=host)


    @defer.inlineCallbacks
    def _changeNick(self, d, room, user, nick, host):
        ur = yield self._fetchInRoster(room, user, host)
        dbuser, dbroom = ur
        n = yield self._dbpool.runWithConnection(self._update_nick, dbroom, dbuser, nick)

        d.callback(n)
        
    def _update_nick(self, conn, dbroom, dbuser, nick):
        cursor = conn.cursor()
        cursor.execute("""UPDATE muc_rooms_roster SET nick = ?
                          WHERE user_id = ? AND room_id = ?""" ,
                       (nick, dbuser, dbroom))
        return nick

    def changeNick(self, room, user, nick, host = None):
        """
        Change the user's nickname in the room
        """
        d = defer.Deferred()
        self._changeNick(d, room, user, nick, host)
        return d
    

    @defer.inlineCallbacks
    def _getNicks(self, d, room, host = None):
        dbroom = yield self._fetchRoom(room, host)
        if dbroom:
            dbroster = yield self._fetchRoster(dbroom[0])
            nicks = []
            for r in dbroster:
                nicks.append(r[8])
            d.callback(nicks)
        else:
            d.errback(failure.Failure('Room Not Found'))
        
    def getNicks(self, room, host = None):
        """
        Get a list of nicknames in a room
        """
        d = defer.Deferred()
        self._getNicks(d, room, host = host)
        return d

    
    def _update_room(self, conn, room, **kwargs):
        new_room = {}
            
        cursor = conn.cursor()        
        
        cursor.execute("""SELECT muc_rooms.id,
                                 muc_rooms.name,
                                 muc_rooms.roomname,
                                 muc_rooms.subject,
                                 muc_rooms.persistent,
                                 muc_rooms.moderated,
                                 muc_rooms.private,
                                 muc_rooms.game,
                                 muc_rooms.history,
                                 muc_rooms.hidden,
                                 muc_rooms.locked,
                                 muc_rooms.description,
                                 muc_rooms.subject_change,
                                 muc_rooms.subjectlocked,
                                 muc_rooms.invitation,
                                 muc_rooms.invites,
                                 muc_rooms.rename,
                                 \"muc_rooms\".\"join\",
                                 muc_rooms.leave,
                                 muc_rooms.privmsg,                                 
                                 muc_rooms.maxusers,
                                 muc_rooms.query_occupants,
                                 muc_rooms.change_nick
                                 
                          FROM muc_rooms WHERE LOWER(name) = LOWER(?) AND hostname = ?""" , (room, kwargs['host']))
        
        
        (new_room['id'],
         new_room['name'], new_room['roomname'], new_room['subject'], new_room['persistent'],
         new_room['moderated'], new_room['private'],
         new_room['game'], new_room['history'], new_room['hidden'],
         new_room['locked'], new_room['description'],
         new_room['subject_change'], new_room['subjectlocked'],
         new_room['invitation'],
         new_room['invites'], new_room['rename'],
         new_room['join'], new_room['leave'],
         new_room['privmsg'], new_room['maxusers'],
         new_room['query_occupants'], new_room['change_nick']
         ) = cursor.fetchone()

        name = room
        
        for arg in kwargs:
            
            if not new_room.has_key(arg):
                # set attributes
                self._set_attribute(conn, new_room['id'], arg, kwargs[arg], kwargs['host'])
                
                    
        new_room.update(kwargs)
        
        cursor.execute("""UPDATE muc_rooms SET
                                           name = ?,
                                           roomname = ?,
                                           description = ?,
                                           change_nick = ?,
                                           subjectlocked = ?,                                           
                                           subject = ?,
                                           subject_change = ?,
                                           persistent = ?,
                                           moderated = ?,
                                           private = ?,
                                           game = ?,
                                           history = ?,
                                           hidden = ?,
                                           invitation = ?,
                                           invites = ?,
                                           privmsg = ?,
                                           rename = ?,
                                           \"join\" = ?,
                                           leave = ?,
                                           maxusers = ?,
                                           query_occupants = ?,
                                           locked = ?
                          WHERE LOWER(name) = LOWER(?) AND hostname = ?""" , (
            new_room['name'], new_room['roomname'],
            self._checkString(new_room['description']), new_room['change_nick'],
            new_room['subjectlocked'], self._checkString(new_room['subject']),
            new_room['subject_change'], new_room['persistent'],
            new_room['moderated'], new_room['private'],
            new_room['game'], new_room['history'], new_room['hidden'],
            new_room['invitation'], new_room['invites'],
            new_room['privmsg'], self._checkString(new_room['rename']), 
            self._checkString(new_room['join']), self._checkString(new_room['leave']),
            new_room['maxusers'], new_room['query_occupants'],
            new_room['locked'], room, kwargs['host']))
        
        return new_room

    
    def updateRoom(self, room, **kwargs):
        """ Update the room attributes """
        return self._dbpool.runWithConnection(self._update_room, room, **kwargs)

    def _hashToDbroom(self, new_room):
        """ Convert a room hash into a dbroom tuple. """
        dbroom = ()
        keys = MAP_DICT.keys()
        keys.sort()
        for key in keys:
            arg = MAP_DICT[key]
            if new_room.has_key(arg):
                dbroom += (new_room[arg],)
            else:
                dbroom += (None, )
        return dbroom
            

    def _dbrosterToHash(self, ret_val, roster):
        """ Convert a roster from the database to a hash """
        
        for m in roster:
            # TODO - create a better way to map these
            u = {}
            
            u['jid'] = m[1]
            u['nick'] = m[8]
            u['status'] = m[10]
            u['show'] = m[9]
            if self._checkBool(m[11]):
                u['legacy'] = True
            else:
                u['legacy'] = False
            set_role = False
            # check for a private room then set to none    
            if self._checkBool(ret_val['invitation']):
                u['role'] = 'none'
                set_role = True
            else:
                if m[7]:
                    u['role'] = m[7]
                else:
                    u['role'] = 'none'
                    set_role = True
            u['affiliation'] = 'none'
            if not m[12] or str(m[12]).strip() == '':
                for a in groupchat.AFFILIATION_LIST:
                    for v in ret_val[a]:
                        if m[1].lower() == v.lower() or \
                                jid_userhost(m[1]).lower() == v.lower():

                            u['role'] = groupchat.AFFILIATION_ROLE_MAP[a]
                            u['affiliation'] = a
                log.msg('legacy data here %s %s %s ' % (m[1], u['role'], u['affiliation']))
            else:
                u['affiliation'] = m[12]
                if set_role:
                    u['role'] = groupchat.AFFILIATION_ROLE_MAP[m[12]]
            
            ret_val['roster'].append(u)
        return ret_val

    def _checkBool(self, val):
        if val and val != 'f' and val != 'False' and val != 'None':
            return True
        return False

    def _checkString(self, val):
        if val:
            return val
        return ''

    def _checkInt(self, val, default = 0):
        if val and val != 'None':
            return int(val)
        return default

    def _dbroomToHash(self, r):
        # may just make this a loop
        
        ret_val = {'name': r[1],
                   'id': r[0]}
            
        ret_val['roomname'] = self._checkString(r[2])
        ret_val['subject'] = self._checkString(r[3])
        ret_val['subject_change'] = self._checkBool(r[4])
        ret_val['persistent'] = self._checkBool(r[5])        
        ret_val['moderated'] = self._checkBool(r[6])        
        ret_val['private'] = self._checkBool(r[7])        
        ret_val['history'] = self._checkInt(r[8], 30)            
        ret_val['game'] = self._checkBool(r[9])
        ret_val['invitation'] = self._checkBool(r[10])
        ret_val['invites'] = self._checkBool(r[11])
        ret_val['hidden'] = self._checkBool(r[12])
        ret_val['locked'] = self._checkBool(r[13])
        ret_val['subjectlocked'] = self._checkBool(r[14])
        ret_val['description'] = self._checkString(r[15])
        ret_val['leave'] = self._checkString(r[16])
        ret_val['join'] = self._checkString(r[18])
        ret_val['rename'] = self._checkString(r[18])
        ret_val['maxusers'] = self._checkInt(r[19], 30)
        ret_val['privmsg'] = self._checkBool(r[20])
        ret_val['change_nick'] = self._checkBool(r[21])            
        ret_val['query_occupants'] = self._checkBool(r[22])

        return ret_val
