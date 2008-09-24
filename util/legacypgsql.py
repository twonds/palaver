# Copyright (c) 2007 Christopher Zorn, OGG, LLC 
# See LICENSE.txt for details
# Converts the legacy muc spool to the new dirDBM one
import sys
from twisted.words.xish import domish, xpath
from twisted.words.protocols.jabber import jid

from twisted.enterprise import adbapi

from palaver import palaver, pgsql_storage
from pyPgSQL import PgSQL


class RoomParser:
    """
    A simple stream parser for configuration files.
    """
    def __init__(self):
        # Setup the parser
        self.stream = domish.elementStream()
        self.stream.DocumentStartEvent = self.onDocumentStart
        self.stream.ElementEvent = self.onElement
        self.stream.DocumentEndEvent = self.onDocumentEnd
        self.hash  = {}
        self.files = {}
        self.room  = {}

    def parse(self, file, room):
        self.room = room
        f   = open(file)
        buf = f.read()
        f.close()
        self.stream.parse(buf)
        return self.room

    def serialize(self, obj):
        if isinstance(obj, domish.Element):
            obj = obj.toXml()
        return obj

    def onDocumentStart(self, rootelem):
        pass


    def onElement(self, element):
        
        if element.name == 'room':
            for c in element.elements():
                if c.name == 'name':
                    self.room['roomname'] = str(c)
                elif c.name=='notice':
                    for n in c.elements():
                        self.room[n.name] = str(n)
                else:
                    if str(c) == '0':
                        self.room[c.name] = False
                    elif str(c) == '1':
                        self.room[c.name] = True
                    else:
                        self.room[c.name] = str(c)
                
        elif element.name == 'list':
            if element.hasAttribute('xdbns'):
                if element['xdbns'] == 'muc:list:owner':
                    for i in element.elements():
                        self.room['owner'].append(i['jid'])
                elif element['xdbns'] == 'muc:list:admin':
                    for i in element.elements():
                        self.room['admin'].append(i['jid'])
                elif element['xdbns'] == 'muc:list:member':
                    for i in element.elements():
                        self.room['member'].append(i['jid'])
                elif element['xdbns'] == 'muc:list:outcast':
                    for i in element.elements():
                        self.room['outcast'].append(i['jid'])
    def onDocumentEnd(self):
        pass


    def _reset(self):
        # Setup the parser
        self.stream = domish.elementStream()
        self.stream.DocumentStartEvent = self.onDocumentStart
        self.stream.ElementEvent = self.onElement
        self.stream.DocumentEndEvent = self.onDocumentEnd

class RoomsParser(RoomParser):    

    def parse(self, file):
        f   = open(file)
        buf = f.read()
        f.close()
        self.stream.parse(buf)
        return self.hash, self.files
        
    def onElement(self, element):
        if element.name == 'registered':
            for i in element.elements():
                name = i.getAttribute('name')
                j  = i.getAttribute('jid')
                njid = jid.JID(name)
                room = unicode(njid.user)
                file = jid.JID(j).user
                self.files[room] = file
                self.hash[room] = {}
                self.hash[room]['name']          = room
                self.hash[room]['roomname']      = room
                self.hash[room]['subject']       = ''
                self.hash[room]['subject_change']= True
                self.hash[room]['persistent']    = True
                self.hash[room]['moderated']     = False
                self.hash[room]['private']       = True
                self.hash[room]['history']       = 10
                self.hash[room]['game']          = False
                self.hash[room]['hidden']        = False
                self.hash[room]['locked']        = False
                self.hash[room]['subjectlocked'] = False
                self.hash[room]['description']   = room
                self.hash[room]['leave']         = ''
                self.hash[room]['join']          = ''
                self.hash[room]['rename']        = ''
                self.hash[room]['maxusers']      = 30
                self.hash[room]['privmsg']       = True
                self.hash[room]['change_nick']   = True


                self.hash[room]['owner']   = []
                self.hash[room]['member']  = []
                self.hash[room]['admin']   = []
                self.hash[room]['outcast'] = []
                self.hash[room]['roster']  = []
            

def fetch_user(cursor, user):
        
    cursor.execute("""SELECT * FROM muc_users WHERE username = %s""",(user,))
    return cursor.fetchone()

def create_user(cursor, user):
    dbuser = fetch_user(cursor,user)
    # TODO - add other values
    if not dbuser:
        cursor.execute("""INSERT INTO muc_users (username)
        VALUES (%s)
        """, (user,))
        dbuser = fetch_user(cursor,user)
    return dbuser

def do_room(conn, room, hostname):
    cursor = conn.cursor()

    cursor.execute("""INSERT INTO muc_rooms (name,
                                             roomname,
                                             subject,
                                             subject_change,
                                             persistent,
 	                                     moderated,
                                             private,
                                             history,
                                             game,
                                             \"hidden\",
                                             \"locked\",
                                             subjectlocked,
                                             description,
                                             \"leave\",
                                             \"join\",
                                             rename,
                                             maxusers,
                                             privmsg,
                                             change_nick,
                                             hostname
                                             )
                          VALUES (%s, %s, %s, %s, %s, %s, %s,
                                  %s, %s, %s, %s, %s, %s, %s,
                                  %s, %s, %s, %s, %s, %s)""" ,
                       (room['name'],
                        room['roomname'],
                        room['subject'],
                        room['subject_change'],
                        room['persistent'],
                        room['moderated'],
                        room['private'],
                        room['history'],
                        room['game'],
                        room['hidden'],
                        room['locked'],
                        room['subjectlocked'],
                        room['description'],
                        room['leave'],
                        room['join'],
                        room['rename'],
                        room['maxusers'],
                        room['privmsg'],
                        room['change_nick'],
                        hostname
                        ))
    
    cursor.execute("""SELECT * FROM muc_rooms WHERE name = %s AND hostname = %s""", (room['name'],hostname))
    dbroom = cursor.fetchone()
    cursor.close()
    

    # do admins , members, owners, etc

    for u in room['admin']:
        cursor = conn.cursor()
        # create a user if not in he user table
        dbuser = create_user(cursor, u)

        cursor.execute("""INSERT INTO muc_rooms_admins (user_id, room_id)
                          VALUES (%s, %s)
                          """, (dbuser[0],dbroom[0]))
        
        
        cursor.close()

    for u in room['member']:
        cursor = conn.cursor()
        # create a user if not in he user table
        dbuser = create_user(cursor, u)
        cursor.execute("""INSERT INTO muc_rooms_members (user_id, room_id)
                          VALUES (%s, %s)
                          """, (dbuser[0],dbroom[0]))
        
        
        cursor.close()        

    for u in room['owner']:
        cursor = conn.cursor()
        # create a user if not in he user table
        dbuser = create_user(cursor, u)
        cursor.execute("""INSERT INTO muc_rooms_owners (user_id, room_id)
                          VALUES (%s, %s)
                          """, (dbuser[0],dbroom[0]))
        
        
        cursor.close()
    for u in room['outcast']:
        cursor = conn.cursor()
        # create a user if not in he user table
        dbuser = create_user(cursor, u)
        cursor.execute("""INSERT INTO muc_rooms_outcasts (user_id, room_id)
                          VALUES (%s, %s)
                          """, (dbuser[0],dbroom[0]))
        
        
        cursor.close()        

    

def main(sdir, conf):
    print 'Convert : %s ' % sdir

    # parse conf file
    cf = None

    p  = palaver.ConfigParser()
    cf = p.parse(conf)
    

    config = {}
    
    backend = getattr(cf.backend,'type',None)
    if backend:
        config['backend'] = str(backend)
        if config['backend'] == 'pgsql':
            user = getattr(cf.backend,'dbuser',None)            
            database = str(getattr(cf.backend,'dbname',''))
            if getattr(cf.backend,'dbpass',None):
                password = str(getattr(cf.backend,'dbpass',''))
            else:
                password = ''
                
            if getattr(cf.backend,'dbhostname',None):
                hostname = str(getattr(cf.backend,'dbhostname',''))
            else:
                hostname = ''
    for elem in cf.elements():
        if elem.name == 'name':
            host     = str(elem)

    _dbpool = PgSQL.connect(
        database=database,
        user=user,
        password=password,
        dsn=hostname,
        client_encoding='utf-8'
        )

    
    rsp = RoomsParser()

    rp  = RoomParser()

    rooms, files = rsp.parse(sdir+'/rooms.xml')
    for f in files:        
        r = files[f]
        print sdir+'/'+str(r)+'.xml'
        room = rp.parse(sdir+'/'+str(r)+'.xml',rooms[f])

        do_room(_dbpool, room, host)
        rp._reset()
    _dbpool.commit()
    
if __name__ == '__main__':
    if len(sys.argv)==2:
        main(sys.argv[1])
    elif len(sys.argv)==3:
        main(sys.argv[1], sys.argv[2])
    else:
        print "Usage : %s <old spool dir> <palaver config file>\n" % sys.argv[0]
