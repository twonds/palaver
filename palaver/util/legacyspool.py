# Copyright (c) 2005 - 2007 Christopher Zorn, OGG, LLC 
# See LICENSE.txt for details
# Converts the legacy muc spool to the new dirDBM one
import sys
from twisted.words.xish import domish, xpath
from twisted.words.protocols.jabber import jid
from twisted.persisted import dirdbm

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
                room = njid.user
                file = jid.JID(j).user
                self.files[room] = file
                self.hash[room] = {}
                self.hash[room]['name']          = room
                self.hash[room]['roomname']      = room
                self.hash[room]['subject']       = ''
                self.hash[room]['subject_change']= True
                self.hash[room]['persistent']    = False
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
            

def main(sdir, newdir=None):
    print 'Convert : %s ' % sdir
    if newdir:
        spool = dirdbm.Shelf(newdir)
    else:
        spool = dirdbm.Shelf(sdir)
    if not spool.has_key('rooms'):
        spool['rooms'] = {}
    rsp = RoomsParser()

    rp  = RoomParser()

    rooms, files = rsp.parse(sdir+'/rooms.xml')
    for f in files:        
        r = files[f]
        print sdir+'/'+str(r)+'.xml'
        room = rp.parse(sdir+'/'+str(r)+'.xml',rooms[f])
        rp._reset()

    spool['rooms'] = rooms
    
if __name__ == '__main__':
    if len(sys.argv)==2:
        main(sys.argv[1])
    elif len(sys.argv)==3:
        main(sys.argv[1], sys.argv[2])
    else:
        print "Usage : %s <old spool dir> [new spool dir]\n" % sys.argv[0]
