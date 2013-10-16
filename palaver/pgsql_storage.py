# Copyright (c) 2005 - 2008 Christopher Zorn, OGG, LLC 
# See LICENSE.txt for details

import string
import thread
import time
from twisted.enterprise import adbapi
from twisted.python import log, failure
from twisted.internet import defer, reactor

from zope.interface import implements
import cPickle as pickle
import groupchat
import storage
import memcache


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

def _encode_escape(buf):
    if type(buf) == type(''):
        buf = unicode(buf, 'utf-8')
    buf = buf.encode('ascii','xmlcharrefreplace')
    buf = buf.replace("\\","")
    buf = buf.replace(" ","sp")
    return buf

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

# also add inverted keys to MAP_DICT_BW so that r[MAP_DICT_BW["id"]] works
MAP_DICT_BW = {}
for k in MAP_DICT.keys():
    MAP_DICT_BW[MAP_DICT[k]] = k

        
class Storage:

    implements(storage.IStorage)
    sadmins = []
    users = {}

    
    def __init__(self, user, database, password=None, hostname=None, port=None, apitype='pyPgSQL.PgSQL', memcache_servers=[]):
        kw = {}
        self.MEMCACHE_SERVERS = memcache_servers
        self.ignore_hidden_cache = False # set this to true if we want to reset hidden rooms in cache
        self._dbpool = None
        conn_string = "dbname=%s" % database
        conn_string = "user=%s %s" % (user, conn_string)
        if password:
            conn_string += " password='%s'" %  password
        if hostname:
            conn_string += " host=%s" % hostname
        else:
            conn_string += " host=''" 
        if port:
            conn_string += " port=%s" % port

        self.apitype = apitype
        if apitype == 'psycopg2':
            
            # test for Connection Factory
            try:
                from twisted.enterprise.adbapi import Psycopg2ConnectionFactory as cf
            except:
                cf = None
            if cf:

                apitype = cf(conn_string,
                             **kw)

                
                #kw['adb_reconnect'] = True
                self._dbpool = adbapi.ConnectionPool(apitype,
                                      **kw
                                      )

        kw['cp_reconnect'] = True
        if not self._dbpool:
            self._dbpool = adbapi.ConnectionPool(apitype,
                                                 conn_string,
                                                 **kw
                                                 )
        
        # load up memcache and flush on start
        self.threadID = thread.get_ident

        # connect to memcache servers
        self.mc_connections = {}

        # need to start up thread pools
        self.running = False
        self.startID = reactor.callWhenRunning(self._start)
	self.shutdownID = None

    def _start(self):
        self.startID = None

        if not self.running:
            self._dbpool.start()
            self.shutdownID = reactor.addSystemEventTrigger('during',
                                                            'shutdown',
                                                            self._finalClose)
            self.running = True

        self.resetCache()

    def _finalClose(self):
        """This should only be called by the shutdown trigger."""
	
	# the following works around issues with trial and reactor
	# starts.  see twisted bug #2498
	
        self.shutdownID = None
	
        self.startID = None

        if self._dbpool:
            self._dbpool.close()
            
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
            return mc.get(key)
        return None
    
    def setInCache(self, key, val, expire=None):
        mc = self.getMemcacheConnection()
        if not mc:
            return 
        # default is to cache for one hour
        if not expire:
            expire = int(time.time() + 3600)
        mc.set(key, val, expire)

    def deleteInCache(self, key):
        mc = self.getMemcacheConnection()
        if not mc:
            return
        mc.delete(key)

    def resetCache(self):
        # flush the cache at component startup
        if len(self.MEMCACHE_SERVERS) > 0:
            mc = memcache.Client(self.MEMCACHE_SERVERS)
            mc.flush_all()
            return True
        
    def _getUserFromCache(self, user):
        user = _encode_escape(user)
        key = u'muc_users:'+user.lower()
        dbuser = self.getFromCache(key)
        if dbuser:
            dbuser = pickle.loads(dbuser)
        return dbuser

    def _setUserInCache(self, user, dbuser):
        user = _encode_escape(user)
        key = u'muc_users:'+user
        self.setInCache(key.lower(), pickle.dumps(dbuser))
        
    def _deleteUserInCache(self, user):
        user = _encode_escape(user)
        key = u'muc_users:'+user.lower()
        user = self.deleteInCache(key)

    def _getRoomFromCache(self, room):
        room = _encode_escape(room)
        key = u'muc_rooms:'+room
        r = self.getFromCache(key.lower())
        if r:
            r = pickle.loads(r)
        return r

    def _setRoomInCache(self, room, dbroom):
        room = _encode_escape(room)
        key = u'muc_rooms:'+room
        self.setInCache(key.lower(), pickle.dumps(dbroom))
        
    def _deleteRoomInCache(self, room):
        key = 'muc_rooms:'+room.lower()
        user = self.deleteInCache(key)


    def _getPublicRoomsFromCache(self, host):
        host = _encode_escape(host)
        key = u'muc_rooms_list_public:'+host
        r = self.getFromCache(key.lower())
        if r:
            r = pickle.loads(r)
        return r

    def _setPublicRoomsInCache(self, host, dbroom):
        host = _encode_escape(host)
        key = u'muc_rooms_list_public:'+host
        self.setInCache(key.lower(), pickle.dumps(dbroom))
        
    def _deletePublicRoomsInCache(self, host):
        key = 'muc_rooms_list_public:'+host.lower()
        user = self.deleteInCache(key)


    def _getHiddenRoomsFromCache(self, host):
        if self.ignore_hidden_cache:
            self.ignore_hidden_cache = False
            return
        host = _encode_escape(host)
        key = u'muc_rooms_list_hidden:'+host
        r = self.getFromCache(key.lower())
        if r:
            r = pickle.loads(r)
        return r

    def _setHiddenRoomsInCache(self, host, dbroom):
        host = _encode_escape(host)
        key = u'muc_rooms_list_hidden:'+host
        self.setInCache(key.lower(), pickle.dumps(dbroom))
        
    def _deleteHiddenRoomsInCache(self, host):
        key = 'muc_rooms_list_hidden:'+host.lower()
        user = self.deleteInCache(key)


    def _getRosterFromCache(self, room_id):
        key = 'muc_rosters:'+str(room_id)
        dr = self.getFromCache(key)
        if dr:
            dr = pickle.loads(dr)
        return dr

    def _setRosterInCache(self, room_id, dbr):
        key = 'muc_rosters:'+str(room_id)
        self.setInCache(key, pickle.dumps(dbr))
        
    def _deleteRosterInCache(self, room_id):
        key = 'muc_rosters:'+str(room_id)
        user = self.deleteInCache(key)


    def _getInRosterFromCache(self, room):
        room = _encode_escape(room)
        key = 'muc_rosters:'+room.lower()
        dr = self.getFromCache(key)
        if dr:
            dr = pickle.loads(dr)
        return dr

    def _setInRosterInCache(self, room, dbr):
        room = _encode_escape(room)
        key = 'muc_rosters:'+room.lower()
        self.setInCache(key, pickle.dumps(dbr))
        
    def _deleteInRosterInCache(self, room):
        room = _encode_escape(room)
        key = 'muc_rosters:'+room.lower()
        user = self.deleteInCache(key)


    def _getAffiliationFromCache(self, room_id, affiliation):
        key = 'muc_affiliations:'+str(affiliation)+str(room_id)
        dr = self.getFromCache(key)
        if dr:
            dr = pickle.loads(dr)
        return dr

    def _setAffiliationInCache(self, room_id, affiliation, dbr):
        key = 'muc_affiliations:'+str(affiliation)+str(room_id)
        self.setInCache(key, pickle.dumps(dbr))
        
    def _deleteAffiliationInCache(self, room_id, affiliation):
        key = 'muc_affiliations:'+str(affiliation)+str(room_id)
        user = self.deleteInCache(key)

    def _getAttributeFromCache(self, room_id, attribute):
        key = 'muc_attributes:'+str(attribute)+str(room_id)
        dr = self.getFromCache(key)
        if dr:
            dr = pickle.loads(dr)
        return dr

    def _setAttributeInCache(self, room_id, attribute, dbr):
        key = 'muc_attributes:'+str(attribute)+str(room_id)
        self.setInCache(key, pickle.dumps(dbr))
        
    def _deleteAttributeInCache(self, room_id, attribute):
        key = 'muc_attributes:'+str(attribute)+str(room_id)
        user = self.deleteInCache(key)


    def _getAttributeListFromCache(self, room_id):
        key = 'muc_attributes:'+str(room_id)
        dr = self.getFromCache(key)
        if dr:
            dr = pickle.loads(dr)
        return dr

    def _setAttributeListInCache(self, room_id, dbr):
        key = 'muc_attributes:'+str(room_id)
        self.setInCache(key, pickle.dumps(dbr))
        
    def _deleteAttributeListInCache(self, room_id):
        key = 'muc_attributes:'+str(room_id)
        user = self.deleteInCache(key)
    

    def _fetch_user(self, conn, user):
        if not user:
            log.msg('No user to fetch?')
            return
        cursor = conn.cursor()
        resource = jid_resource(user)
        dbuser = self._getUserFromCache(user)
        if dbuser:
            return dbuser
        cursor.execute("""SELECT id, username, presence, resource FROM muc_users WHERE LOWER(username) = LOWER(%s) """, (user,))
        dbuser = cursor.fetchone()
        self._setUserInCache(user, dbuser)
        return dbuser


    def _create_user(self, conn, user):
        cursor = conn.cursor()
        resource = jid_resource(user)

        dbuser = self._fetch_user(conn, user)
        # TODO - add other values
        
        if not dbuser and self.users.has_key(user):
            dbuser = self.users[user]
        
        if not dbuser:
            try:        
                cursor.execute("""INSERT INTO muc_users (username, resource)
            VALUES (%s, %s)
            """, (user, resource))
            except:
                pass
                

            dbuser = self._fetch_user(conn, user)
            
            self.users[user] = dbuser
        elif self.users.has_key(user):
            del self.users[user]
                    
        return dbuser


    def _add_roster(self, conn, dbroom, dbuser, nick, status = '', show = '', legacy=True, host = None, affiliation='none', role='participant'):        
        cursor = conn.cursor()

        if not dbuser:
            raise Exception, 'User can not be added to the roster.'

        args = (int(dbuser[0]), int(dbroom[0]), nick, status, show, legacy, affiliation, role)
        cursor.execute("""SELECT 1 FROM muc_rooms_roster WHERE user_id = %s AND room_id = %s""", (dbuser[0], dbroom[0], ))
        c = cursor.fetchone()
        if not c:
            cursor.execute("""INSERT INTO muc_rooms_roster 
                          (user_id, room_id, nick, status, show, legacy, affiliation, role)
                          VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, args)
        roster = self._getRosterFromCache(dbroom[0])
        ul = (int(dbuser[0]), dbuser[1], 
              dbuser[2], dbuser[3],
              None, dbroom[0],
              dbuser[0], role, 
              nick, show, status,
              legacy, affiliation,)
        if roster != None:
            roster.append(ul)
            self._setRosterInCache(dbroom[0], roster)
        self._setInRosterInCache(dbroom[1]+dbuser[1]+host, ul)
        return True
    
    

    def _fetch_in_roster(self, conn, room, user, host, nick=None):
        in_roster = self._getInRosterFromCache(room+user+host)
        if in_roster:
            return in_roster
        nick_sql = ''
        cursor = conn.cursor()
        if nick:
            nick_sql = "AND LOWER(muc_rooms_roster.nick) = LOWER(%s)"
            args = (nick, room , user, host)
        else:
            args = (room , user, host)
        ROSTER_SQL = """SELECT   muc_users.id,
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
                          FROM muc_rooms_roster, muc_rooms, muc_users
                          WHERE muc_rooms_roster.user_id = muc_users.id
                          %s
                          AND   LOWER(muc_rooms.name) = LOWER(%s)
                          AND   LOWER(muc_users.username) = LOWER(%s)
                          AND   muc_rooms.hostname = %s
                          AND   muc_rooms_roster.room_id = muc_rooms.id""" % (nick_sql, '%s', '%s','%s')

        cursor.execute(ROSTER_SQL, args)
        ul = cursor.fetchone()
        if not ul:
            ul = []
        self._setInRosterInCache(room+user+host, ul)
        return ul

            
    def _fetch_room(self, conn, room, host):
        r = self._getRoomFromCache(room+host)
        if r:
            return r
        cursor = conn.cursor()
        try:
            if type(room) == type(''):
                room = unicode(room, 'utf-8')

            val_str = string.join([' "%s"' % (val,) for key, val in MAP_DICT.iteritems()], ", ")            
            cursor.execute("""SELECT %s FROM muc_rooms WHERE LOWER(name) = LOWER(%s) AND hostname = %s""" % (val_str, '%s', '%s'), (room, host))        
            r = cursor.fetchone()
                            
        except:
            r = None
        if r:
            self._setRoomInCache(room+host, r)
        return r
    
    def _fetch_roster(self, conn, room_id, host = None):
        roster = self._getRosterFromCache(room_id)
        if roster:
            return roster
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
                          WHERE muc_rooms_roster.room_id = %s
                          AND muc_rooms_roster.user_id = muc_users.id
        """, (room_id, ))        
        roster = cursor.fetchall()
        self._setRosterInCache(room_id, roster)
        return roster
    
    def _fetch_attribute(self, conn, room_id, attr, host = None):
        pval = self._getAttributeFromCache(room_id, attr)
        if pval:
            return pval
        cursor = conn.cursor()
        cursor.execute("""SELECT value FROM muc_roomattributess
                          WHERE muc_roomattributess.room_id = %s
                          AND muc_roomattributess.key = %s
        """, (room_id, attr))        
        row = cursor.fetchone()
        if row:
            pval = row[0]
            self._setAttributeInCache(room_id, attr, pval)
        return pval
        

    def _fetch_affiliation(self, conn, affiliation, sql, room_id):
        """fetch an affiliation from cache or database
        """
        a = self._getAffiliationFromCache(room_id, affiliation)
        if a != None:
            return a
        cursor = conn.cursor()
        cursor.execute(sql)
        a = cursor.fetchall()
        self._setAffiliationInCache(room_id, affiliation, a)
        return a

    def _fetch_owners(self, conn, room_id, host = None):
        sql = """SELECT
                          muc_users.id,
                          muc_users.username,
                          muc_users.presence,
                          muc_users.resource,
                          muc_rooms_owners.id,
                          muc_rooms_owners.room_id,
                          muc_rooms_owners.user_id
                         
                          FROM muc_users, muc_rooms_owners
                          WHERE muc_rooms_owners.room_id = %d
                          AND muc_rooms_owners.user_id = muc_users.id """ % (room_id, )
        return self._fetch_affiliation(conn, 'owner', sql, room_id)
    
    def _fetch_outcasts(self, conn, room_id, host = None):
        sql = """SELECT
                          muc_users.id,
                          muc_users.username,
                          muc_users.presence,
                          muc_users.resource,
                          muc_rooms_outcasts.id,
                          muc_rooms_outcasts.room_id,
                          muc_rooms_outcasts.user_id,
                          muc_rooms_outcasts.reason
                          FROM muc_users, muc_rooms_outcasts
                          WHERE muc_rooms_outcasts.room_id = %d
                          AND muc_rooms_outcasts.user_id = muc_users.id
        """ % (room_id, )
        return self._fetch_affiliation(conn, 'outcast', sql, room_id)
    
    def _fetch_admins(self, conn, room_id, host = None):
        sql = """SELECT
                          muc_users.id,
                          muc_users.username,
                          muc_users.presence,
                          muc_users.resource,
                          muc_rooms_admins.id,
                          muc_rooms_admins.room_id,
                          muc_rooms_admins.user_id
                          FROM muc_users, muc_rooms_admins
                          WHERE muc_rooms_admins.room_id = %d
                          AND muc_rooms_admins.user_id = muc_users.id
        """ % (room_id, )
        return self._fetch_affiliation(conn, 'admin', sql, room_id)
        
    
    def _fetch_members(self, conn, room_id, host = None):
        sql = """SELECT
                          muc_users.id,
                          muc_users.username,
                          muc_users.presence,
                          muc_users.resource,
                          muc_rooms_members.id,
                          muc_rooms_members.room_id,
                          muc_rooms_members.user_id
                          FROM muc_users, muc_rooms_members
                          WHERE muc_rooms_members.room_id = %d
                          AND muc_rooms_members.user_id = muc_users.id
        """ % (room_id, )
        return self._fetch_affiliation(conn, 'member', sql, room_id)
    
    def _fetch_players(self, conn, room_id, host = None):
        sql = """SELECT
                          muc_users.id,
                          muc_users.username,
                          muc_users.presence,
                          muc_users.resource,
                          muc_rooms_players.id,
                          muc_rooms_players.room_id,
                          muc_rooms_players.user_id
                          FROM muc_users, muc_rooms_players
                          WHERE muc_rooms_players.room_id = %d
                          
                          AND muc_rooms_players.user_id = muc_users.id
        """ % (room_id, )

        return self._fetch_affiliation(conn, 'player', sql, room_id)


    def _clear_owners(self, conn, room_id):
        cursor = conn.cursor()
        cursor.execute("""DELETE FROM muc_rooms_owners
                          WHERE muc_rooms_owners.room_id = %s
                          
        """, (room_id,))
        self._deleteAffiliationInCache(room_id, 'owner')
        return True

    def _clear_outcasts(self, conn, room_id):
        cursor = conn.cursor()
        cursor.execute("""DELETE FROM muc_rooms_outcasts
                          WHERE muc_rooms_outcasts.room_id = %s
                          
        """, (room_id,))
        
        self._deleteAffiliationInCache(room_id, 'outcast')
        return True

    def _clear_admins(self, conn, room_id):
        cursor = conn.cursor()
        cursor.execute("""DELETE FROM muc_rooms_admins
                          WHERE muc_rooms_admins.room_id = %s
                         
        """, (room_id,))
        self._deleteAffiliationInCache(room_id, 'admin')
        return True
    
    def _clear_members(self, conn, room_id):
        cursor = conn.cursor()
        cursor.execute("""DELETE FROM muc_rooms_members
                          WHERE muc_rooms_members.room_id = %s
                       
        """, (room_id,))
        self._deleteAffiliationInCache(room_id, 'member')
        return True
    
    def _clear_players(self, conn, room_id):
        cursor = conn.cursor()
        cursor.execute("""DELETE FROM muc_rooms_players
                          WHERE muc_rooms_players.room_id = %s
                          """, (room_id,))
        self._deleteAffiliationInCache(room_id, 'player')
        return True

    def _delete_owner(self, conn, room_id, user_id):
        cursor = conn.cursor()
        cursor.execute("""DELETE FROM muc_rooms_owners
                          WHERE muc_rooms_owners.room_id = %s
                          AND muc_rooms_owners.user_id = %s
        """, (room_id, user_id))
        self._deleteAffiliationInCache(room_id, 'owner')
        return True

    def _delete_outcast(self, conn, room_id, user_id):
        cursor = conn.cursor()
        cursor.execute("""DELETE FROM muc_rooms_outcasts
                          WHERE muc_rooms_outcasts.room_id = %s
                          AND muc_rooms_outcasts.user_id = %s
        """, (room_id, user_id))
        self._deleteAffiliationInCache(room_id, 'outcast')
        return True

    def _delete_admin(self, conn, room_id, user_id):
        cursor = conn.cursor()
        cursor.execute("""DELETE FROM muc_rooms_admins
                          WHERE muc_rooms_admins.room_id = %s
                          AND muc_rooms_admins.user_id = %s
        """, (room_id, user_id))
        self._deleteAffiliationInCache(room_id, 'admin')
        return True
    
    def _delete_member(self, conn, room_id, user_id):
        cursor = conn.cursor()
        cursor.execute("""DELETE FROM muc_rooms_members
                          WHERE muc_rooms_members.room_id = %s
                          AND muc_rooms_members.user_id = %s
        """, (room_id, user_id))
        self._deleteAffiliationInCache(room_id, 'member')
        return True
    
    def _delete_player(self, conn, room_id, user_id):
        cursor = conn.cursor()
        cursor.execute("""DELETE FROM muc_rooms_players
                          WHERE muc_rooms_players.room_id = %s
                          AND muc_rooms_players.user_id = %s
        """, (room_id, user_id))
        self._deleteAffiliationInCache(room_id, 'player')
        return True    

    def _update_role(self, conn, dbroom, dbuser, role):
        cursor = conn.cursor()
        cursor.execute("""UPDATE muc_rooms_roster SET role = %s
        WHERE user_id = %s AND room_id = %s""",
                       (role, int(dbuser), int(dbroom)))
        self._deleteRosterInCache(int(dbroom))
        return True

    def _update_affiliation(self, conn, dbroom, dbuser, a):
        updated = False
        cursor = conn.cursor()
        try:
            cursor.execute("""UPDATE muc_rooms_roster SET affiliation = %s
        WHERE user_id = %s AND room_id = %s""",
                       (a, int(dbuser), int(dbroom)))
            updated = True
        except:
            updated = False
        self._deleteAffiliationInCache(dbroom, a)
        self._deleteRosterInCache(dbroom)
        return updated

    def _check_nick(self, conn, room_id, user, nick):
        roster = self._getRosterFromCache(room_id)
        if roster:
            for r in roster:
                if r[8].lower()==nick.lower():
                    return True
            
        cursor = conn.cursor()
        cursor.execute("""SELECT nick FROM muc_rooms_roster
                          WHERE lower(nick) = lower(%s)
                          AND room = %s""", (nick, room_id))
        # we should use rowcount?

        if not cursor.fetchone() is None:
            return True
        return False

    def _change_status(self, conn, dbroom, dbuser, show = '', status = '', legacy = False, host = None):        
        cursor = conn.cursor()
        cursor.execute("""UPDATE muc_rooms_roster SET \"show\" = %s , \"status\" = %s , legacy = %s
        WHERE user_id = %s AND room_id = %s 
        """ , (show, status, legacy, str(dbuser), str(dbroom)))
        self._deleteRosterInCache(int(dbroom))
        return True
    
    def _create_room(self, conn, room, owner, new_room):
        cursor = conn.cursor()
                
        cursor.execute("""select nextval('muc_rooms_id_seq');""")
        dbroom_id = cursor.fetchone()[0]
        cursor.execute("""INSERT INTO muc_rooms (id, name, roomname, subject, persistent,
 	                                     moderated, private,
	                                     game, hidden, locked,
                                             hostname, change_nick,
                                             invites, privmsg
                                             )
                          VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 't', %s, %s)""",
                       (dbroom_id, room, room,
                        new_room['subject'], new_room['persistent'],
                        new_room['moderated'], new_room['private'],
                        new_room['game'], new_room['hidden'],
                        new_room['locked'], new_room['host'],
                        new_room['invites'], new_room['privmsg']))
        self._deletePublicRoomsInCache(new_room['host'])
        self.ignore_hidden_cache = True
        return dbroom_id


    @defer.inlineCallbacks
    def _createRoom(self, d, room, owner, **kwargs):
        """
        Create the user and room, then insert user into owners
        """
        # NOTE - we should already know the room does not exist
        new_room = {
            'name': room,
            'subject': None,
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

        if kwargs['legacy']:
            new_room['locked'] = False

        dbroom_id = yield self._dbpool.runWithConnection(self._create_room, room, owner, new_room)
        new_room['id'] = dbroom_id
        dbuser = None
        owner = jid_userhost(owner)    
        if not dbuser:    
            dbuser = yield self._dbpool.runWithConnection(self._create_user, owner)
                
        if not dbuser:
            d.errback(failure.Failure(Exception, 'Owner can not be added'))                    
        
        m = yield self._dbpool.runWithConnection(self._insert_affiliation, 'owner', dbroom_id, dbuser[0])
        
        d.callback(room)
        
    def createRoom(self, room, owner, **kwargs):
        d = defer.Deferred()
        self._createRoom(d, room, owner, **kwargs)
        return d

    def _clearRoster(self, conn, room, user, host):
        self._deleteInRosterInCache(room+user+host)

    def _fetchInRoster(self, room, user, host):
        return self._dbpool.runWithConnection(self._fetch_in_roster, room, user, host)

    
    @defer.inlineCallbacks
    def _setRole(self, d, room, user, role, host):
        
        ur = yield self._fetchInRoster(room, user, host)
        if ur:
            dbuser, dbroom = ur[0], ur[5]
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
            cursor.execute("""UPDATE muc_roomattributess SET value = %s WHERE key = %s AND room_id = %s """ , (pval, attr, dbroom))
        else:        
            cursor.execute("""INSERT INTO muc_roomattributess (room_id, key, value) VALUES (%s, %s, %s)""" , (dbroom, attr, pval))

        self._setAttributeInCache(dbroom, attr, pval)
        return pval

    @defer.inlineCallbacks
    def _setAffiliation(self, d, room, user, affiliation, reason, host):
        if not host:
            d.errback(failure.Failure(Exception, 'Host is None'))
        
        dbuser = None
        dbroom = None
        if affiliation != 'none' and affiliation not in groupchat.AFFILIATION_LIST:
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
        
        users = [dbuser]
        if resource:
            noresource = yield self._fetchUser(username)
            if noresource:
                users = [dbuser, noresource]
        else:
            # grab affiliations with user in it
            for a in groupchat.AFFILIATION_LIST:
                # skip player affiliations if not a game room
                if a == "player" and not dbroom[MAP_DICT_BW["game"]]:
                    continue

                a_list = yield self._fetchAffiliations(dbroom[0], a)
                cuser = user.lower()
                for u in a_list:
                    if u[1].lower() == cuser:
                        users.append(u)
                        break
                    elif jid_userhost(u[1]).lower() == jid_userhost(cuser):
                        users.append(u)
                        break

        for u in users:
            for a in groupchat.AFFILIATION_LIST:
                fnc = getattr(self,'_delete_'+a, None)            
                if fnc:
                    try:
                        df = yield self._dbpool.runWithConnection(fnc, dbroom[0], u[0])
                    except:
                        log.err()
                        log.msg('Error in removing affiliation %s %s' % (str(dbroom), str(dbuser),))

            
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
            log.msg('We did not remove the affiliation %s %s %s' % (str(host), str(dbroom), str(u),))


        # update roster
        u = yield self._dbpool.runWithConnection(self._update_affiliation, dbroom[0], dbuser[0], affiliation)

        d.callback(True)


            
            
    def _insert_affiliation(self, conn, affiliation, dbroom, dbuser, reason = None):
        cursor = conn.cursor()
        if affiliation == 'outcast' and reason:
            INSERT_SQL = """INSERT INTO muc_rooms_%s
                                 (user_id, room_id, reason)
                          VALUES (%s, %s, %s)""" % (affiliation+'s', '%s', '%s', '%s') 
            args = (dbuser, dbroom, reason.__str__(), )

        else:
            INSERT_SQL = """INSERT INTO muc_rooms_%s
                                 (user_id, room_id)
                          VALUES (%s, %s)""" % (affiliation+'s', '%s', '%s')
            args = (dbuser, dbroom,)

        try:
            cursor.execute(INSERT_SQL, args)
        except:
            log.msg(INSERT_SQL % args)
            log.err()
            return False
        self._deleteAffiliationInCache(dbroom, affiliation)
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
        roster = self._getRosterFromCache(room)
        if roster:
            return roster[7]
        cursor = conn.cursor()

        cursor.execute("""SELECT muc_rooms_roster.role
                          FROM muc_rooms, muc_rooms_roster, muc_users
                          WHERE LOWER(muc_rooms.name) = LOWER(%s) AND
                                LOWER(muc_users.username) = LOWER(%s) AND
                                muc_rooms.id = muc_rooms_roster.room_id AND
                                muc_users.id = muc_rooms_roster.user_id AND
                                muc_rooms.hostname = %s""", (room, user, host))

        
        res = cursor.fetchone()
        if res:
            role = res[0]
        return role
            
        
    def getRole(self, room, user, host = None):
        return self._dbpool.runWithConnection(self._get_role, room, user, host)

    @defer.inlineCallbacks
    def _getAffiliation(self, d, room, user, host):
        affiliation = 'none'

        dbroom = yield self._fetchRoom(room, host)
        resource = jid_resource(user)
        if dbroom is None:
            log.msg('Room not found ', room)
            d.errback(failure.Failure(Exception, 'Room not found'))
            return

        for a in groupchat.AFFILIATION_LIST:
            # skip player affiliations if not a game room
            if a == "player" and not dbroom[MAP_DICT_BW["game"]]:
                continue
            
            a_list = yield self._fetchAffiliations(dbroom[0], a)
            if a == 'admin':
                a_list += self.sadmins
            cuser = user.lower()
            for u in a_list:
                if u[1].lower() == cuser:
                    affiliation = a
                    break
                elif jid_userhost(u[1]).lower() == jid_userhost(cuser):
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


    def _inRoom(self, room, user, nick, host):
        return self._dbpool.runWithConnection(self._fetch_in_roster, room, user, host, nick=nick)
    
    @defer.inlineCallbacks
    def _joinRoom(self, d, room, user, nick, status = '', show = '', legacy= True, host = None):
        joined = False
        ul = yield self._inRoom(room, user, nick, host)
        
        if not ul:
            # add user to the roster and user
            dbuser = yield self._fetchUser(user)
            
            if not dbuser:
                dbuser = yield self._dbpool.runWithConnection(self._create_user, user)
            
            dbroom = yield self._fetchRoom(room, host)
            # grab affiliations
            affiliation = yield self.getAffiliation(room, user, host)
            role = 'participant'
            
            if affiliation:
                role = groupchat.AFFILIATION_ROLE_MAP[affiliation]
            elif dbroom[6]:
                role = 'visitor'
            
            try:

                a = yield self._dbpool.runWithConnection(self._add_roster,
                                                         dbroom, dbuser,
                                                         nick, status,
                                                         show, legacy, host,
                                                         affiliation=affiliation,
                                                         role=role)                    
                joined = a
                
            except:
                log.err()
                joined = False
                log.msg('Can not add to roster %s %s %s'  % (room, user, nick, ))
                # d.errback(failure.Failure(Exception, 'Can not join roster twice'))
        

        d.callback(joined)
            
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

    
    
    @defer.inlineCallbacks
    def _changeStatus(self, d, room, user, show = None, status = None, legacy = False, host = None):

        ur = yield self._fetchInRoster(room, user, host)

        if ur:
            dbuser, dbroom = ur[0], ur[5]
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
            WHERE user_id = %s AND room_id = %s
            """, (int(dbuser), int(dbroom)))
        except:
            log.err()
            return False
        roster = self._getRosterFromCache(dbroom)
        # find and remove from cache
        if roster:
            for m in roster:
                if m[0] == dbuser:
                    roster.pop(roster.index(m))
                    break
            self._setRosterInCache(dbroom, roster)
        #self._deleteRosterInCache(int(dbroom))
        return True

    @defer.inlineCallbacks
    def _partRoom(self, d, room, user, nick, host):
        # check for room types, grab role and affiliation
        ur = yield self._inRoom(room, user, nick, host=host)
                
        if ur and len(ur)>5:
            dbuser, dbroom = ur[0], ur[5]
            u = self._dbUserToHash(ur)
            u['role'] = 'none'
            u['affiliation'] = 'none'

            p = yield self._dbpool.runWithConnection(self._part_room, dbroom, dbuser)
            self._dbpool.runWithConnection(self._clearRoster, room, user, host)
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
                c.execute("""SELECT persistent FROM muc_rooms WHERE LOWER(name) = LOWER(%s) AND hostname = %s""", (room, host))
                p = c.fetchone()
                if p and p[0]:
                    # This means room is persistent and should not be deleted
                    return False
        # dbroom = self._fetch_room(c, room, host)

        c.execute("""DELETE FROM muc_rooms WHERE LOWER(name) = LOWER(%s) AND hostname = %s """, (room, host))
        
        if c.rowcount == 1:
            self._deleteRoomInCache(room+host)
            self._deletePublicRoomsInCache(host)
            self.ignore_hidden_cache = True
            return True
        return False

    
    def _get_attributes(self, conn, dbroom):
        pval = self._getAttributeListFromCache(dbroom)
        if pval != None:
            return pval
        cursor = conn.cursor()
        # get attributes
        cursor.execute("SELECT key, value FROM muc_roomattributess WHERE room_id = %s""", (dbroom, ))
        retval = cursor.fetchall()
        self._setAttributeListInCache(dbroom, retval) 
        return retval

    
        
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
                            

    def _fetchAffiliations(self, room_id, affiliation):
        """
        Grab an affilition list from the cache or db
        """
        fnc = getattr(self, '_fetch_'+affiliation+'s', None)
        d  = self._dbpool.runWithConnection(fnc, int(room_id))
        return d
                

    @defer.inlineCallbacks
    def _getRoom(self, d, room, host, frm = None):
        """
        """
        ret_val = None
                
        r = yield self._fetchRoom(room, host)

        if r:
            # create a cleaner way to map these
            ret_val = self._dbroomToHash(r)

            attribs = yield self._fetchRoomAttributes(r[0])
            for key, val in attribs:
                try:
                    ret_val[key] = pickle.loads(str(val))
                except:
                    pass

            roster = yield self._fetchRoster(int(r[0]))

            members = yield self._fetchAffiliations(int(r[0]), 'member')
            ret_val['member'] = self._appendAffiliations(r[0], members)
            admins = yield self._fetchAffiliations(int(r[0]), 'admin')
            ret_val['admin'] = self._appendAffiliations(r[0], admins)
            owners = yield self._fetchAffiliations(int(r[0]), 'owner')
            ret_val['owner'] = self._appendAffiliations(r[0], owners)

            if r[MAP_DICT_BW["game"]]:
                players = yield self._fetchAffiliations(int(r[0]), 'player')
                ret_val['player'] = self._appendAffiliations(r[0], players)

            outcasts  = yield self._fetchAffiliations(int(r[0]), 'outcast')

            ret_val['outcast'] = {}
            ret_val['reason'] = {}

            for m in outcasts:
                ret_val['outcast'][m[1]] = m[1]
                if len(m)>7:
                    ret_val['reason'][m[1]] = m[7]


            ret_val['roster'] = {}

            ret_val = self._dbrosterToHash(ret_val, roster)

        d.callback(ret_val)

    def _appendAffiliations(self, room_id, affiliations):
        val = {}
        for m in affiliations:
            u = m[1].lower()
            val[u] = u

        return val

    def getRoom(self, room, host, frm=None):
        """ Grab a room from the backend """
        d = defer.Deferred()
        try:
            self._getRoom(d, room, host, frm = frm)
        except:
            d.callback(None)
        return d

    def _getPublicRooms(self, cursor, host, frm):
        """
        grab all rooms that are public to users.
        """
        rooms = self._getPublicRoomsFromCache(host)
        if rooms != None:
            return rooms
        SELECT_SQL = "SELECT name, hostname, hidden FROM muc_rooms WHERE hidden = 'f' AND hostname = %s "
            
        cursor.execute(SELECT_SQL, (host,))
        results = cursor.fetchall()
        self._setPublicRoomsInCache(host, results)
        return results

    def _getHiddenRooms(self, cursor, host, users, show_players=False):
        """
        grab hidden rooms that are only viewable by the user requesting
        """
        results   = []
        # TODO - cache these results
        if not users:
            return results
        key = host.lower() + string.join(["%d" % (u[0],) for u in users])
        results = self._getHiddenRoomsFromCache(key)
        if results != None:
            return results
        roster_sql  = "AND (" +string.join([" muc_rooms_roster.user_id = %d" % (u[0],) for u in users], " OR ") + ")"
        owners_sql  = "AND (" +string.join([" muc_rooms_owners.user_id = %d" % (u[0],) for u in users], " OR ") + ")"
        admins_sql  = "AND (" +string.join([" muc_rooms_admins.user_id = %d" % (u[0],) for u in users], " OR ") + ")"
        members_sql = "AND (" +string.join([" muc_rooms_members.user_id = %d" % (u[0],) for u in users], " OR ") + ")"
        if show_players:
            players_sql = "AND (" +string.join([" muc_rooms_players.user_id = %d" % (u[0],) for u in users], " OR ") + ")"
            players_join_sql = """LEFT OUTER JOIN muc_rooms_players
                        ON (muc_rooms.id = muc_rooms_players.room_id %s) """ % (players_sql,)
        else:
            players_join_sql = ""
        
        SELECT_SQL = """SELECT muc_rooms.name, muc_rooms.hostname, muc_rooms.hidden 
                        FROM muc_rooms

                        LEFT OUTER JOIN muc_rooms_roster
                        ON (muc_rooms.id = muc_rooms_roster.room_id %s)

                        LEFT OUTER JOIN muc_rooms_owners
                        ON (muc_rooms.id = muc_rooms_owners.room_id %s)

                        LEFT OUTER JOIN muc_rooms_admins
                        ON (muc_rooms.id = muc_rooms_admins.room_id %s)

                        LEFT OUTER JOIN muc_rooms_members
                        ON (muc_rooms.id = muc_rooms_members.room_id %s)

                        %s

                        WHERE 
                             muc_rooms.hidden = 't' 
                         AND muc_rooms.hostname = %s
                       """ % (roster_sql, owners_sql, 
                              admins_sql, members_sql, 
                              players_join_sql, '%s',)
            
        cursor.execute(SELECT_SQL, (host, ))
        results = cursor.fetchall()
        self._setHiddenRoomsInCache(key, results)
        return results
    def _doGetRoomsList(self, host, frm):

        def doGetRooms(conn, host, frm):
            cursor = conn.cursor()

            public_rooms = self._getPublicRooms(cursor, host, frm)
            hidden_rooms = []
            if frm:
                user     = jid_userhost(frm)
                resource = jid_resource(frm)
                dbuser   = self._fetch_user(conn, frm)
                dbusers  = []
                if dbuser:
                    dbusers.append(dbuser)
                if resource:
                    dbu = self._fetch_user(conn, user)
                    if dbu:
                        dbusers.append(dbu)

                hidden_rooms = self._getHiddenRooms(cursor, host, dbusers)

            return public_rooms + hidden_rooms

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
        dbuser, dbroom = ur[0], ur[5]
        n = yield self._dbpool.runWithConnection(self._update_nick, dbroom, dbuser, nick)

        d.callback(n)
        
    def _update_nick(self, conn, dbroom, dbuser, nick):
        cursor = conn.cursor()
        cursor.execute("""UPDATE muc_rooms_roster SET nick = %s
                          WHERE user_id = %s AND room_id = %s""",
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
                                 
                          FROM muc_rooms WHERE LOWER(name) = LOWER(%s) AND hostname = %s""", (room,kwargs['host']))
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
                
        self._deleteAttributeListInCache(new_room['id']) 
        new_room.update(kwargs)
        cursor.execute("""UPDATE muc_rooms SET
                                           name = %s,
                                           roomname = %s,
                                           description = %s,
                                           change_nick = %s,
                                           subjectlocked = %s,                                           
                                           subject = %s,
                                           subject_change = %s,
                                           persistent = %s,
                                           moderated = %s,
                                           private = %s,
                                           game = %s,
                                           history = %s,
                                           hidden = %s,
                                           invitation = %s,
                                           invites = %s,
                                           privmsg = %s,
                                           rename = %s,
                                           \"join\" = %s,
                                           leave = %s,
                                           maxusers = %s,
                                           query_occupants = %s,
                                           locked = %s
                          WHERE LOWER(name) = LOWER(%s) AND hostname = %s""", (
                new_room['name'], new_room['roomname'],
                new_room['description'], new_room['change_nick'],
                new_room['subjectlocked'], new_room['subject'],
                new_room['subject_change'], new_room['persistent'],
                new_room['moderated'], new_room['private'],
                new_room['game'], new_room['history'], new_room['hidden'],
                new_room['invitation'], new_room['invites'],
                new_room['privmsg'], new_room['rename'], new_room['join'], new_room['leave'],
                new_room['maxusers'], new_room['query_occupants'],
                new_room['locked'], room, kwargs['host']))
        self._deleteRoomInCache(new_room['name']+new_room['host'])
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
            
    def _dbUserToHash(self, m, ret_val = None):
        u = {}
        
        u['jid'] = m[1]
        u['nick'] = m[8]
        u['status'] = m[10]
        u['show'] = m[9]
        if m[11]:
            u['legacy'] = True
        else:
            u['legacy'] = False
        # check for a private room then set to none    
            
        u['role'] = 'none'
        set_role = False
        if ret_val and not ret_val['invitation'] and m[7]:
            u['role'] = m[7]
        elif not ret_val and m[7]:
            u['role'] = m[7]
        else:    
            set_role = True

        u['affiliation'] = 'none'
        if ret_val and not m[12] or str(m[12]).strip() == '':
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
        return u
                
    def _dbrosterToHash(self, ret_val, roster):
        """ Convert a roster from the database to a hash """
        for m in roster:
            # TODO - create a better way to map these
            u = self._dbUserToHash(m, ret_val)
            ret_val['roster'][u['jid'].lower()] = u

        return ret_val

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
        ret_val['join'] = self._checkString(r[17])
        ret_val['rename'] = self._checkString(r[18])
        ret_val['maxusers'] = self._checkInt(r[19], 30)
        ret_val['privmsg'] = self._checkBool(r[20])
        ret_val['change_nick'] = self._checkBool(r[21])            
        ret_val['query_occupants'] = self._checkBool(r[22])

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
    
