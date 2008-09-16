# -*- coding: utf8 -*-
# Copyright (c) 2005 - 2007  OGG, LLC 
# See LICENSE.txt for details
import os
import sys, sha
from twisted.trial import unittest
import time
from twisted.words.protocols.jabber import jid
from twisted.internet import defer, protocol, reactor
from twisted.application import internet, service
from twisted.words.xish import domish, xpath

import pickle

from twisted.python import log

try:
    from twisted.words.protocols.jabber.component import IService
except:
    from twisted.words.protocols.jabber.ijabber import IService

from twisted.words.protocols.jabber import component, xmlstream

from palaver import storage, groupchat, palaver
from palaver import pgsql_storage
from palaver import dir_storage, memory_storage

from palaver.test import  readlog

PASSWORD = 'palaveriscool'
HOSTNAME = 'palaver.localhost'
PORT     = 5437

    
class DummyTransport:
    def __init__(self, xmlparser):
        #self.list = list
        
        self.xmlparser = xmlparser
 	
    def write(self, bytes):
        # should we reset or use the stream?
        self.xmlparser.parse(bytes)
        #self.list.append(elem)

    def loseConnection(self, *args, **kwargs):
        self.xmlparser._reset()



class TestStorage(pgsql_storage.Storage):
    """
    alter some storage methods to count queries and check other tests
    """
    test_attribute_cache_sets = 0
    test_attributelist_cache_sets = 0
    test_hidden_cache_sets = 0

    def _setAttributeInCache(self, room_id, attribute, dbr):
        key = 'muc_attributes:'+str(attribute)+str(room_id)
        self.setInCache(key, pickle.dumps(dbr))    
        self.test_attribute_cache_sets += 1
        

    def _setAttributeListInCache(self, room_id, dbr):
        key = 'muc_attributes:'+str(room_id)
        self.setInCache(key, pickle.dumps(dbr))
        self.test_attributelist_cache_sets += 1
        

    def _setHiddenRoomsInCache(self, host, dbroom):
        host = pgsql_storage._encode_escape(host)
        key = u'muc_rooms_list_hidden:'+host
        self.setInCache(key.lower(), pickle.dumps(dbroom))
        self.test_hidden_cache_sets += 1

class ProtocolTests(unittest.TestCase):
    """
    """

    def setUp(self):
        """
        Set up harness and palaver connection to the harness
        """
        
        # PALAVER set up
        
        # set up Jabber Component
        sm = component.buildServiceManager(HOSTNAME, PASSWORD,
                                           ("tcp:"+HOSTNAME+":"+str(PORT) ))

        # Turn on verbose mode
        palaver.LogService().setServiceParent(sm)

                

        # allow for other storage in tests
        st = TestStorage(user='tofu',
                         database='muc',
                         hostname=None,
                         password=None,
                         port=None,
                         apitype='psycopg2',
                         memcache_servers = ['127.0.0.1:11211']
                         )
        
        self.groupchat_service = groupchat.GroupchatService(st)
                    
        c = IService(self.groupchat_service)
        c.setServiceParent(sm)        

        self.room_service = groupchat.RoomService()
                
        self.room_service.setServiceParent(self.groupchat_service)
        IService(self.room_service).setServiceParent(sm)


        self.admin_service = groupchat.AdminService()

        self.admin_service.setServiceParent(self.groupchat_service)
        IService(self.admin_service).setServiceParent(sm)
        

        self.palaver_service = palaver.PalaverService()
        self.palaver_service.setServiceParent(sm)
        
        self.palaver_factory = sm.getFactory()
        # set up xmlstream for palaver

        self.wstream = readlog.XmlParser()
        
        self.palaver_xs = self.palaver_factory.buildProtocol(None)
        self.palaver_xs.transport = DummyTransport(self.wstream)
        

        # Indicate that palaver is connected 
        self.palaver_xs.connectionMade()
        
        self.palaver_xs.dataReceived("<stream:stream xmlns='jabber:component:accept' xmlns:stream='http://etherx.jabber.org/streams' from='localhost' id='12345'>")


        hv = sha.new("%s%s" % ("12345", PASSWORD)).hexdigest()
 	
        self.assertEquals(str(self.wstream.entity.handshake), hv)
 	
        self.palaver_xs.dataReceived("<handshake/>")
        
        
        
        # check if the xmlstream was set and jabber id
        self.assertEquals(self.palaver_service.xmlstream, self.palaver_xs)
        self.assertEquals(self.palaver_service.jid, HOSTNAME)


    def _waitForData(self, childNumber, d, timeout):
        timeout -= 0.25
        if len(self.wstream.entity.children)>=childNumber or timeout <= 0:
            d.callback(True)
        else:
            reactor.callLater(0.25, self._waitForData, childNumber, d, timeout)
            

    def _testCreate(self, test_elem, frm):
        self.assertEquals(xpath.matches("/presence[@from='"+frm+"']/x[@xmlns='http://jabber.org/protocol/muc#user']/item[@role='moderator']", test_elem), 1)
        

    def doWait(self, cb, num, timeout=5):
        d = defer.Deferred()
        self._waitForData(num,d, timeout)
        d.addCallback(cb)
        return d

    def _createRoom(self, frm, to):
        CLIENT_XML = """<presence from='%s' to='%s'/>""" % (frm, to, )        
        self.palaver_xs.dataReceived(CLIENT_XML)
    
    def test10000CreateRoom(self):
        """ Test Create a Room .........................................................."""
        def _cbCreateRoom(t):
            self.assertEquals(t, True)
            test_elem = self.wstream.entity.children.pop()
                        
            
            # Next element should be a presence broadcast
            self.assertEquals(test_elem.name, 'presence')
            frm = 'darkcave@%s/thirdwitch' % HOSTNAME
            self._testCreate(test_elem, frm)
            
            if len(self.wstream.entity.children)>1:
                # Joining room instead of creating it
                child_count = len(self.wstream.entity.children)
                for i in range(1, child_count):
                    test_elem = self.wstream.entity.children.pop()
                    self.assertEquals(test_elem.name, 'presence')
        
        
        self._createRoom('hag66@shakespeare.lit/pda', 'darkcave@%s/thirdwitch' % (HOSTNAME, ))
        
        return self.doWait(_cbCreateRoom, 2)


    def testSpecialCharacters(self):
        """ Test Create a Room .........................................................."""
        def _cbCreateRoom(t):
            self.assertEquals(t, True)
            test_elem = self.wstream.entity.children.pop()
                        
            
            # Next element should be a presence broadcast
            self.assertEquals(test_elem.name, 'presence')
            frm = 'dark\\20cave@%s/thirdwitch' % HOSTNAME
            self._testCreate(test_elem, frm)
            
            if len(self.wstream.entity.children)>1:
                # Joining room instead of creating it
                child_count = len(self.wstream.entity.children)
                for i in range(1, child_count):
                    test_elem = self.wstream.entity.children.pop()
                    self.assertEquals(test_elem.name, 'presence')
        
        
        self._createRoom('hag66@shakespeare.lit/pda', 'dark\\20cave@%s/thirdwitch' % (HOSTNAME, ))
        
        return self.doWait(_cbCreateRoom, 2)



    def testLeaveAndDeleteRoom(self):
        """ Test leave and delete a room .........................................................."""

        def test109(t):
            test_elem = self.wstream.entity.children.pop()
            self.failUnless(xpath.matches("/presence/x/status[@code='201']", test_elem), 'Invalid room create.')
                        
            

        def testRoom(t):
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
            
            # join the room again and see if we get the status code
            CLIENT_XML = """<presence from='%s' to='%s'>
    <x xmlns='http://jabber.org/protocol/muc'/>
 </presence>""" % ('hag66@shakespeare.lit/pda', 'delete@%s/thirdwitch' % (HOSTNAME, ))        
            self.palaver_xs.dataReceived(CLIENT_XML)
            return self.doWait(test109, 2)
    
        def leaveRoom(t):
            test_elem = self.wstream.entity.children.pop()
            self.failUnless(xpath.matches("/iq[@type='result']", test_elem), 'Invalid iq result.')
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()

            CLIENT_XML = """<presence from='%s' to='%s' type='unavailable'>
    <x xmlns='http://jabber.org/protocol/muc'/>
 </presence>""" % ('hag66@shakespeare.lit/pda', 'delete@%s/thirdwitch' % (HOSTNAME, ))        


            self.palaver_xs.dataReceived(CLIENT_XML)
            return self.doWait(testRoom, 2)

        

        def _cbCreateRoom(t):
            self.assertEquals(t, True)
            test_elem = self.wstream.entity.children.pop()
                        
            frm = 'delete@%s/thirdwitch' % HOSTNAME
            self._testCreate(test_elem, frm)

            # send config
            CONFIG_XML = """<iq from='hag66@shakespeare.lit/pda' id='arbiter_kds_9877' type='set' to='delete@%s'>
            <query xmlns='http://jabber.org/protocol/muc#admin'>
             <x xmlns='jabber:x:data' type='submit'>
              <field var='FORM_TYPE'>
                <value>http://jabber.org/protocol/muc#roomconfig</value>
              </field>
              <field var='muc#roomconfig_whois'><value>anyone</value></field>
             </x></query></iq>""" % (HOSTNAME, )
            self.palaver_xs.dataReceived(CONFIG_XML)
            return self.doWait(leaveRoom, 2)
            
                
        CLIENT_XML = """<presence from='%s' to='%s'>
    <x xmlns='http://jabber.org/protocol/muc'/>
 </presence>""" % ('hag66@shakespeare.lit/pda', 'delete@%s/thirdwitch' % (HOSTNAME, ))        
        self.palaver_xs.dataReceived(CLIENT_XML)
        return self.doWait(_cbCreateRoom, 2)

        

    def testRoomNotFound(self):
        """
        Test a strange bug that happens when lots of presence comes in.
        """
        def doChecks(t):
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
                self.failUnless(xpath.matches("/presence[@type='error']", test_elem)==0, 'Should not get presence errors')
            
        
        def doPresence(t):
            PRESENCE_XML = """<presence xmlns='jabber:client' to='centralpark@chat.chesspark.com/attila_turzo@chesspark.com' from='attila_turzo@chesspark.com/cpc'>
        <x xmlns='http://jabber.org/protocol/muc'/>
        <show>away</show>
        <status>Busy</status>
</presence>
<presence xmlns='jabber:client' to='help@chat.chesspark.com/attila_turzo@chesspark.com' from='attila_turzo@chesspark.com/cpc'>
     <x xmlns='http://jabber.org/protocol/muc'/>
     <show>away</show>
     <status>Busy</status>
     </presence>
     <presence xmlns='jabber:client' to='magyarok@chat.chesspark.com/attila_turzo@chesspark.com' from='attila_turzo@chesspark.com/cpc'>
     <x xmlns='http://jabber.org/protocol/muc'/>
     <show>away</show>
     <status>Busy</status>
     </presence>
     <presence xmlns='jabber:client' to='freestyle@chat.chesspark.com/attila_turzo@chesspark.com' from='attila_turzo@chesspark.com/cpc'>
     <x xmlns='http://jabber.org/protocol/muc'/>
     <show>away</show>
     <status>Busy</status></presence>
     <presence xmlns='jabber:client' to='tournament@chat.chesspark.com/attila_turzo@chesspark.com' from='attila_turzo@chesspark.com/cpc'>
     <x xmlns='http://jabber.org/protocol/muc'/>
     <show>away</show>
     <status>Busy</status>
     </presence>
     <presence xmlns='jabber:client' to='dev@chat.chesspark.com/attila_turzo@chesspark.com' from='attila_turzo@chesspark.com/cpc'>
     <x xmlns='http://jabber.org/protocol/muc'/>
     <show>away</show>
     <status>Busy</status>
    </presence>
"""
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
            self.palaver_xs.dataReceived(PRESENCE_XML)

            return self.doWait(doChecks, 10)


        CREATE_XML = """<presence xmlns='jabber:client' to='centralpark@chat.chesspark.com/createadmin@chesspark.com' from='createadmin@chesspark.com/cpc'/>
<presence xmlns='jabber:client' to='help@chat.chesspark.com/createadmin@chesspark.com' from='createadmin@chesspark.com/cpc' />
     <presence xmlns='jabber:client' to='magyarok@chat.chesspark.com/createadmin@chesspark.com' from='createadmin@chesspark.com/cpc' />
     <presence xmlns='jabber:client' to='freestyle@chat.chesspark.com/createadmin@chesspark.com' from='createadmin@chesspark.com/cpc' />
     <presence xmlns='jabber:client' to='tournament@chat.chesspark.com/createadmin@chesspark.com' from='createadmin@chesspark.com/cpc' />

     <presence xmlns='jabber:client' to='dev@chat.chesspark.com/createadmin@chesspark.com' from='createadmin@chesspark.com/cpc' />
"""
        self.palaver_xs.dataReceived(CREATE_XML)
        
        return self.doWait(doPresence, 10)

    def testUserIsNone(self):
        """
        There is a bug that palaver can not pick up users in the roster, even when they are.

        2007/08/02 08:03 -0500 [XmlStream,client] 1186059832.19 - RECV: <message xmlns='jabber:client' type='groupchat' from='arbiter.chesspark.com' to='823146@games
.chesspark.com'><game xmlns='http://onlinegamegroup.com/xml/chesspark-01' id='823146' black='valamigo@chesspark.com' white='robopawn@chesspark.com'><move sid
e='white' player='robopawn@chesspark.com'>d3c3</move><time side='black' control='0'>1464.00055242</time><time side='white' control='0'>1794.01822162</time></
game></message><message xmlns='jabber:client' from='trainer@chesspark.com/TrainingBot' type='groupchat' to='823180@games.chesspark.com/TrainingBot'><body>Hel
lo, please solve this problem. You can also send &apos;help&apos; if you are stuck. Your side is black</body></message>
2007/08/02 08:03 -0500 [-] trainer@chesspark.com/TrainingBot
2007/08/02 08:03 -0500 [-] User is none, something is wrong
2007/08/02 08:03 -0500 [-] MUC Error : 
2007/08/02 08:03 -0500 [-] [Failure instance: Traceback: <class 'palaver.groupchat.RoomNotFound'>: 
        /home/chesspark/production/lib/python/twisted/internet/posixbase.py:228:mainLoop
        /home/chesspark/production/lib/python/twisted/internet/base.py:533:runUntilCurrent
        /home/chesspark/production/lib/python/twisted/internet/defer.py:239:callback
        /home/chesspark/production/lib/python/twisted/internet/defer.py:304:_startRunCallbacks
        --- <exception caught here> ---
        /home/chesspark/production/lib/python/twisted/internet/defer.py:317:_runCallbacks
        /home/chesspark/production//lib/python/palaver/groupchat.py:397:process



        """

        def doJoin(t):
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
                
            self.fail('Not Implemented')

        def doMore(t):
            PRESENCE_XML = """
            <presence
    from='notfound@shakespeare.lit/throne'
    to='notfound@%s/testing' />
    """ % (HOSTNAME, )
            
            self.palaver_xs.dataReceived(PRESENCE_XML)
            
            return self.doWait(doJoin, 2)
        
            

        PRESENCE_XML = """
<presence
    from='kinghenryv@shakespeare.lit/throne'
    to='notfound@%s/king' />
    """ % (HOSTNAME, )

        self.palaver_xs.dataReceived(PRESENCE_XML)
        
        return self.doWait(doMore, 2)


    def testUpdateRoomArgs(self):
        """ Need to test configuring arguments outside the room table. See _update_room for why"""

        def checkDb(r):
            self.failUnless(int(r['history'])==60,'Wrong history count')


        def configRoom(t):
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
            # check database
            self.groupchat_service.storage.getRoom('roomargs', HOSTNAME).addCallback(checkDb)


        def create(t):
            test_elem = self.wstream.entity.children.pop()
            # update history size
            frm = 'roomargs@%s/king' % HOSTNAME
            self._testCreate(test_elem, frm)
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
            # send config
            CONFIG_XML = """<iq from='kinghenryv@shakespeare.lit/throne' id='arbiter_kds_9877' type='set' to='roomargs@%s'>
            <query xmlns='http://jabber.org/protocol/muc#admin'>
             <x xmlns='jabber:x:data' type='submit'>
              <field var='FORM_TYPE'>
                <value>http://jabber.org/protocol/muc#roomconfig</value>
              </field>
              <field var='muc#roomconfig_whois'><value>anyone</value></field>
              <field var='history'><value>60</value></field>
             </x></query></iq>""" % (HOSTNAME, )
            self.palaver_xs.dataReceived(CONFIG_XML)
            return self.doWait(configRoom, 2)

        PRESENCE_XML = """
<presence
    from='kinghenryv@shakespeare.lit/throne'
    to='roomargs@%s/king' />
    """ % (HOSTNAME, )

        self.palaver_xs.dataReceived(PRESENCE_XML)
        
        return self.doWait(create, 2)

    def test61(self):
        """ Test Section 6.1 http://www.xmpp.org/extensions/xep-0045.html#disco-component """

        def _cb61(t):
            test_elem = self.wstream.entity.children.pop()
            self.assertNotEquals(test_elem['type'],'error')
            # test for correct namespace
            self.assertEquals(test_elem.query.uri,'http://jabber.org/protocol/disco#info')

            got_muc = False
        
            for f in test_elem.query.elements():
                if f.name == 'feature' and f['var'] == 'http://jabber.org/protocol/muc':
                    got_muc = True
            self.assertEquals(got_muc, True)

        CLIENT_XML = """
           <iq from='hag66@shakespeare.lit/pda' xmlns='jabber:client'
           id='disco1'
           to='%s'
           type='get'>
           <query xmlns='http://jabber.org/protocol/disco#info'/>
           </iq>
        """ % (HOSTNAME)


        self.palaver_xs.dataReceived(CLIENT_XML)

        return self.doWait(_cb61, 2)

    def test62(self):
        """ Test Section 6.2 http://www.xmpp.org/extensions/xep-0045.html#disco-rooms ..."""

        def _cb62(t):
            test_elem = self.wstream.entity.children.pop()
        
            self.assertNotEquals(test_elem['type'],'error')
            # test for correct namespace
            self.assertEquals(test_elem.query.uri,'http://jabber.org/protocol/disco#items')

        def _doDisco(t):
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
            CLIENT_XML = """
           <iq from='hag66@shakespeare.lit/pda' xmlns='jabber:client'
           id='disco1'
           to='%s'
           type='get'>
           <query xmlns='http://jabber.org/protocol/disco#items'/>
           </iq>
           """ % (HOSTNAME)


            self.palaver_xs.dataReceived(CLIENT_XML)
            
            return self.doWait(_cb62, 2)

        PRESENCE_XML = """
<presence
    from='kinghenryv@shakespeare.lit/throne'
    to='lusófonos@%s/king' />
    """ % (HOSTNAME, )

        self.palaver_xs.dataReceived(PRESENCE_XML)
        
        return self.doWait(_doDisco, 2)

    def test63(self):
        """ Test Section 6.3 http://www.xmpp.org/extensions/xep-0045.html#disco-roominfo."""
        def _cb63(t):
            test_elem = self.wstream.entity.children.pop()
            
            self.assertNotEquals(test_elem['type'],'error')
            # test for correct namespace
            self.assertEquals(test_elem.query.uri,'http://jabber.org/protocol/disco#info')
            # TODO - add more tests to this
            # palaver returns extended disco
            

        CLIENT_XML = """
           <iq from='hag66@shakespeare.lit/pda' xmlns='jabber:client'
           id='disco3'
           to='darkcave@%s'
           type='get'>
           <query xmlns='http://jabber.org/protocol/disco#info'/>
           </iq>
        """ % (HOSTNAME)

        self.palaver_xs.dataReceived(CLIENT_XML)

        return self.doWait(_cb63, 2)

    def test64(self):
        """ Test Section 6.4 http://www.xmpp.org/extensions/xep-0045.html#disco-roomitems"""

        def _cb64(t):
            test_elem = self.wstream.entity.children.pop()
            self.assertEquals(test_elem['type'],'result')
            self.assertEquals(test_elem['id'],'disco4')
            # TODO - add test for public and private items
            
        DISCO_ITEMS_XML = """
<iq from='hag66@shakespeare.lit/pda'
    id='disco4'
    to='darkcave@%s'
    type='get'>
  <query xmlns='http://jabber.org/protocol/disco#items'/>
</iq>
        """ % (HOSTNAME,)
        
        self.palaver_xs.dataReceived(DISCO_ITEMS_XML)

        return self.doWait(_cb64, 2)


    def test65(self):
        """ Test Section 6.5 http://www.xmpp.org/extensions/xep-0045.html#disco-occupant."""

        def _eb65(t):
            test_elem = self.wstream.entity.children.pop()
            self.assertEquals(test_elem['type'],'error')
            self.assertEquals(test_elem['id'],'disco6')
            self.assertEquals(getattr(test_elem.error,'bad-request').name,'bad-request')
            
        def _cb65(t):
            test_elem = self.wstream.entity.children.pop()
            self.assertEquals(test_elem['type'],'result')
            self.assertEquals(test_elem['id'],'disco5')
            # TODO - add test for public and private items

            DISCO_ITEMS_XML = """
<iq from='lordscroop@shakespeare.lit/pda'
    id='disco6'
    to='darkcave@%s/oldhag'
    type='get'>
  <query xmlns='http://jabber.org/protocol/disco#items'/>
</iq>
        """ % (HOSTNAME,)
        
            self.palaver_xs.dataReceived(DISCO_ITEMS_XML)

            return self.doWait(_eb65, 2)

            
        DISCO_ITEMS_XML = """
<iq from='hag66@shakespeare.lit/pda'
    id='disco5'
    to='darkcave@%s/oldhag'
    type='get'>
  <query xmlns='http://jabber.org/protocol/disco#items'/>
</iq>
        """ % (HOSTNAME,)
        
        self.palaver_xs.dataReceived(DISCO_ITEMS_XML)
        
        return self.doWait(_cb65, 2)


    def test71(self):
        """ Test Section 7.1 http://www.xmpp.org/extensions/xep-0045.html#enter ........."""

        def _cbJoin(t):
            child_count = len(self.wstream.entity.children)
            found_from = False
            for i in range(1, child_count):
                test_elem = self.wstream.entity.children.pop()
                self.assertEquals(test_elem.name, 'presence')
                frm = 'darkcave@%s/palaver' % HOSTNAME

                if test_elem['from'] == frm:
                    found_from = xpath.matches("/presence/x[@xmlns='http://jabber.org/protocol/muc#user']/item[@role='participant']", test_elem)
                    
            # TODO - add the rest of the section
            self.failUnless(found_from, 'Did not find correct from presence.')
        def sendJoin(t):
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
            PRESENCE_XML = """
<presence
    from='palaver@shakespeare.lit/pda'
    to='darkcave@%s/palaver'/>
        """ % (HOSTNAME,)

            self.palaver_xs.dataReceived(PRESENCE_XML)
            
            return self.doWait(_cbJoin, 2)


        PRESENCE_XML = """
<presence
    from='test71@shakespeare.lit/pda'
    to='darkcave@%s/test71'/>
        """ % (HOSTNAME,)

        self.palaver_xs.dataReceived(PRESENCE_XML)
        
        return self.doWait(sendJoin, 2)

    def test71a(self):
        """ Test Section 7.1.1 http://www.xmpp.org/extensions/xep-0045.html#enter-gc ...."""

        def _cbJoin(t):
            test_elem = self.wstream.entity.children.pop()
            self.assertEquals(xpath.matches("/presence[@type='error']/error[@code='400']/jid-malformed", test_elem), 1)
            
        PRESENCE_XML = """
<presence
    from='nonick@shakespeare.lit/pda'
    to='darkcave@%s'/>
        """ % (HOSTNAME,)

        self.palaver_xs.dataReceived(PRESENCE_XML)
        
        return self.doWait(_cbJoin, 2)

    def test71b(self):
        """ Test Section 7.1.3 http://www.xmpp.org/extensions/xep-0045.html#enter-pres   ."""

        def _cbJoin(t):
            test_elem = self.wstream.entity.children.pop()
            self.assertEquals(xpath.matches("/presence[@from='newcave@%s/palaver']/x[@xmlns='http://jabber.org/protocol/muc#user']/item[@affiliation='owner']"%(HOSTNAME,), test_elem), 1)

        PRESENCE_XML = """
<presence
    from='palaver@shakespeare.lit/pda'
    to='newcave@%s/palaver'/>
        """ % (HOSTNAME,)

        self.palaver_xs.dataReceived(PRESENCE_XML)
        
        return self.doWait(_cbJoin, 2)


    def testClearHistory(self):

        def _cbCache(t):
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
            
            self.failUnless(test_elem['type']=='result', 'Did not get a result from command')
        
        def _doAdHoc(t):
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
                
                AD_HOC_XML = """
<iq type='set' from='tofu@thetofu.com/admin' to='sysadmin@%s' id='exec1'>
   <command xmlns='http://jabber.org/protocol/commands'
           node='clearhistory'
           action='execute'/>
</iq>""" % (HOSTNAME,)

        
                self.palaver_xs.dataReceived(AD_HOC_XML)
        
                return self.doWait(_cbCache, 2)
        
        PRESENCE_XML = """<presence to='sysadmin@%s/tofu' from='tofu@thetofu.com/admin' />""" % (HOSTNAME,)

        self.palaver_xs.dataReceived(PRESENCE_XML)

        return self.doWait(_doAdHoc, 2)

    def testClearCache(self):
        """
        Test an ad hoc command to clear cache.
        """
        
        def _cbCache(t):
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
            
            self.failUnless(test_elem['type']=='result', 'Did not get a result from command')
        

        AD_HOC_XML = """<iq type='set' from='tofu@thetofu.com/admin' to='sysadmin@%s' id='exec1'>
   <command xmlns='http://jabber.org/protocol/commands'
           node='clearcache'
           action='execute'/>
</iq>""" % (HOSTNAME,)

        
        self.palaver_xs.dataReceived(AD_HOC_XML)
        
        return self.doWait(_cbCache, 2)

        


    def testHistoryOrder(self):
        """ Test to make sure presence comes before history.                            ."""
        def finish(t):
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
                self.assertEqual(test_elem.name, 'presence')

        def testHistory(t):
            
            test_elem = self.wstream.entity.children.pop()
            self.failUnless(test_elem.name == 'message', 'Messages need to be last')

            mtest  = filter(lambda el: xpath.matches("/message" , el), self.wstream.entity.children)
            #self.failUnless(len(mtest)==4,'Did not get the correct number of messages')
            
            ptest  = filter(lambda el: xpath.matches("/presence" , el), self.wstream.entity.children)
            #self.failUnless(len(ptest)==10,'Did not get the correct number of presence stanzas')

            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
                
                
            # leave room

            PRESENCE_XML = """
                    <presence
    from='palaver@shakespeare.lit/pda'
    to='darkcave@%s/palaverHistory' type='unavailable'/>
            <presence
    from='history@shakespeare.lit/pda'
    to='darkcave@%s/history' type='unavailable'/>
        """ % (HOSTNAME, HOSTNAME, )

            self.palaver_xs.dataReceived(PRESENCE_XML)

            return self.doWait(finish, 4)

        def sendPresence(t):
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
                self.assertEqual(test_elem.name, 'message')

            PRESENCE_XML = """
                    <presence
    from='history@shakespeare.lit/pda'
    to='darkcave@%s/history'/>
        """ % (HOSTNAME,)

            self.palaver_xs.dataReceived(PRESENCE_XML)

            return self.doWait(testHistory, 14)

        def sendMessages(t):
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
            # send messages 
            MESSAGE_XML = """
<message xmlns='jabber:client' to='darkcave@%s' from='palaver@shakespeare.lit/pda' type='groupchat'>
  <body>3</body>
  </message>
  <message xmlns='jabber:client' to='darkcave@%s' from='palaver@shakespeare.lit/pda' type='groupchat'>
  <body>2</body>
  </message>
  <message xmlns='jabber:client' to='darkcave@%s' from='palaver@shakespeare.lit/pda' type='groupchat'>
  <body>1</body>
  </message>
  <message xmlns='jabber:client' to='darkcave@%s' from='palaver@shakespeare.lit/pda' type='groupchat'>
  <body>contact</body>
  </message>
        """ % (HOSTNAME, HOSTNAME, HOSTNAME, HOSTNAME)

            self.palaver_xs.dataReceived(MESSAGE_XML)
            
            return self.doWait(sendPresence, 16)
        PRESENCE_XML = """
                    <presence
    from='palaver@shakespeare.lit/pda'
    to='darkcave@%s/palaverHistory'/>
        """ % (HOSTNAME,)

        self.palaver_xs.dataReceived(PRESENCE_XML)
        
        return self.doWait(sendMessages, 2)
        
        
    def testInvalidNick(self):
        """ Test for no resource to='darkcave@chat.chesspark.com@chat.chesspark.com' .... """
        def _cbJoin(t):
            test_elem = self.wstream.entity.children.pop()
            self.assertEquals(xpath.matches("/presence[@type='error']/error[@code='400']/jid-malformed", test_elem), 1)
            
        PRESENCE_XML = """
<presence
    from='nonick@shakespeare.lit/pda'
    to='darkcave@%s@%s'/>
        """ % (HOSTNAME, HOSTNAME)

        self.palaver_xs.dataReceived(PRESENCE_XML)
        
        return self.doWait(_cbJoin, 2)


    def test72(self):
        """ Test Section 7.2 http://www.xmpp.org/extensions/xep-0045.html#exit .........."""

        def _cbLeave(t):
            child_count = len(self.wstream.entity.children)
            for i in range(1, child_count):
                test_elem = self.wstream.entity.children.pop()
                self.assertEquals(test_elem.name, 'presence')
                if test_elem['from'] == 'darkcave@%s/palaver' % (HOSTNAME,):
                    self.assertEquals(xpath.matches("/presence[@type='unavailable']/x[@xmlns='http://jabber.org/protocol/muc#user']/item[@role='none']", test_elem), 1)

            

        PRESENCE_XML = """<presence
    from='palaver@shakespeare.lit/pda'
    to='darkcave@%s/palaver'
    type='unavailable'/>""" % (HOSTNAME,)

        self.palaver_xs.dataReceived(PRESENCE_XML)
        
        return self.doWait(_cbLeave, 2)

    def test73(self):
        """ Test Section 7.3 http://www.xmpp.org/extensions/xep-0045.html#changenick ...."""

        def _cbJoin(t):
            child_count = len(self.wstream.entity.children)
            for i in range(1, child_count):
                test_elem = self.wstream.entity.children.pop()
                self.assertEquals(test_elem.name, 'presence')
                frm = 'darkcave@%s/change_nick' % HOSTNAME
                if test_elem['from'] == frm:
                    self.assertEquals(xpath.matches("/presence/x[@xmlns='http://jabber.org/protocol/muc#user']/item[@role='participant']", test_elem), 1)
                if test_elem['from'] == 'darkcave@%s/palaver' % (HOSTNAME,):
                    self.assertEquals(xpath.matches("/presence[@type='unavailable']/x[@xmlns='http://jabber.org/protocol/muc#user']/item[@role='participant']", test_elem), 1)
                    self.assertEquals(xpath.matches("/presence[@type='unavailable']/x[@xmlns='http://jabber.org/protocol/muc#user']/status[@code='303']", test_elem), 1)
                    
            # TODO - add the rest of the section
            
        
        PRESENCE_XML = """
<presence
    from='palaver@shakespeare.lit/pda'
    to='darkcave@%s/change_nick'/>
        """ % (HOSTNAME,)

        self.palaver_xs.dataReceived(PRESENCE_XML)
        
        return self.doWait(_cbJoin, 2)
    
    
    def test74(self): 
        """ Test Section 7.4 http://www.xmpp.org/extensions/xep-0045.html#changepres ...."""

        def _cb74(t):
            # grab elements to test
            child_count = len(self.wstream.entity.children)
            for i in range(1, child_count):
                test_elem = self.wstream.entity.children.pop()
                self.assertEquals(test_elem.name, 'presence')
                if test_elem['from'] == 'darkcave@%s/oldhag' % (HOSTNAME,):
                    self.assertEquals(str(test_elem.status),'I am ready to discuss wikka')
                    self.assertEquals(str(test_elem.show),'chat')
                if test_elem['from'] == 'darkcave@%s/testhag' % (HOSTNAME,):
                    self.assertEquals(xpath.matches("/presence/x[@xmlns='http://jabber.org/protocol/muc#user']/item[@role='participant']", test_elem), 1)


        def _cbChangeStatus(t):
            child_count = len(self.wstream.entity.children)
            for i in range(1, child_count):
                test_elem = self.wstream.entity.children.pop()
                self.assertEquals(test_elem.name, 'presence')
                if test_elem['from'] == 'darkcave@%s/oldhag' % (HOSTNAME,):
                    self.assertEquals(str(test_elem.status),'I am ready to discuss wikka')
                    self.assertEquals(str(test_elem.show),'chat')

            PRESENCE_XML = """
<presence
    from='test@shakespeare.lit/laptop'
    to='darkcave@%s/testhag' />
""" % (HOSTNAME, )


            self.palaver_xs.dataReceived(PRESENCE_XML)
        
            return self.doWait(_cb74, 3)

        def _cbJoin(t):
            
            child_count = len(self.wstream.entity.children)
            for i in range(1, child_count):
                test_elem = self.wstream.entity.children.pop()
                self.assertEquals(test_elem.name, 'presence')
                if test_elem['from'] == 'darkcave@%s/oldhag' % (HOSTNAME,):
                    self.assertEquals(str(test_elem.status),'gone where the goblins go')
                    self.assertEquals(str(test_elem.show),'xa')
            
            CHANGE_STATUS_XML = """
<presence
    from='wiccarocks@shakespeare.lit/laptop'
    to='darkcave@%s/oldhag'>
  <show>chat</show>
  <status>I am ready to discuss wikka</status>
</presence>
""" % (HOSTNAME, )

            self.palaver_xs.dataReceived(CHANGE_STATUS_XML)

            return self.doWait(_cbChangeStatus, 3)
                            
                    
        JOIN_STATUS_XML = """
<presence
    from='wiccarocks@shakespeare.lit/laptop'
    to='darkcave@%s/oldhag'>
  <show>xa</show>
  <status>gone where the goblins go</status>
</presence>
        """ % (HOSTNAME, )

        self.palaver_xs.dataReceived(JOIN_STATUS_XML)
                
        return self.doWait(_cbJoin, 3)


    def test75(self): 
        """ Test Section 7.5 http://www.xmpp.org/extensions/xep-0045.html#invite ...."""

        def _cbInvite(t):
            child_count = len(self.wstream.entity.children)
            
            test_elem = self.wstream.entity.children.pop()
                
            self.failUnless(test_elem.name=='message',
                            'Not a message returned')
            self.failUnless(test_elem['to']=='hecate@shakespeare.lit',
                            'The message was sent to the wrong person')
            return True
        
        def _cbJoin(t):
            
            child_count = len(self.wstream.entity.children)
            for i in range(1, child_count):
                test_elem = self.wstream.entity.children.pop()
                self.assertEquals(test_elem.name, 'presence')
                if test_elem['from'] == 'darkcave@%s/oldhag' % (HOSTNAME,):
                    self.assertEquals(str(test_elem.status),'gone where the goblins go')
                    self.assertEquals(str(test_elem.show),'xa')
            
            INVITE_XML = """
<message
    from='wiccarocks@shakespeare.lit/desktop'
    to='darkcave@%s'>
  <x xmlns='http://jabber.org/protocol/muc#user'>
    <invite to='hecate@shakespeare.lit'>
      <reason>
        Hey Hecate, this is the place for all good witches!
      </reason>
    </invite>
  </x>
</message>
""" % (HOSTNAME, )

            self.palaver_xs.dataReceived(INVITE_XML)

            return self.doWait(_cbInvite, 2)
                            
                    
        JOIN_STATUS_XML = """
<presence
    from='wiccarocks@shakespeare.lit/laptop'
    to='darkcave@%s/oldhag'>
  <show>xa</show>
  <status>gone where the goblins go</status>
</presence>
        """ % (HOSTNAME, )

        self.palaver_xs.dataReceived(JOIN_STATUS_XML)
                
        return self.doWait(_cbJoin, 3)


    def test79(self): 
        """ Test Section 7.9 http://www.xmpp.org/extensions/xep-0045.html#message ...."""

        def _cbInvite(t):
            
            mtest  = filter(lambda el: xpath.matches("/message", el), self.wstream.entity.children)
            
            self.failUnless(len(mtest)==2,'Did not get the correct number of messages')

            user1  = filter(lambda el: xpath.matches("/message[@to='wiccarocks@shakespeare.lit/laptop']", el), mtest)
            self.failUnless(len(user1)==1,'Did not get the correct number of messages')

            user2  = filter(lambda el: xpath.matches("/message[@to='79@shakespeare.lit/laptop']", el), mtest)

            self.failUnless(len(user2)==1,'Did not get the correct number of messages')

            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
                
        
        def _cbJoin(t):
            ptest  = filter(lambda el: xpath.matches("/presence", el), self.wstream.entity.children)
            self.failUnless(len(ptest)>1, 'Invalid number of presence stanzas')
                        
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
                        
            MESSAGE_XML = """
<message
    from='wiccarocks@shakespeare.lit/laptop'
    to='test79@%s' type='groupchat'>
  <x xmlns='http://jabber.org/protocol/muc#user' />
  <body>This is a test of the palaver broadcast system.</body>
</message>
""" % (HOSTNAME, )

            self.palaver_xs.dataReceived(MESSAGE_XML)

            return self.doWait(_cbInvite, 3)

        def _cbJoin1(t):
            
            JOIN_STATUS_XML = """
<presence
    from='79@shakespeare.lit/laptop'
    to='test79@%s/79'>
</presence>
            """ % (HOSTNAME,  )

            self.palaver_xs.dataReceived(JOIN_STATUS_XML)
                
            return self.doWait(_cbJoin, 5)

                            
                    
        JOIN_STATUS_XML = """
<presence
    from='wiccarocks@shakespeare.lit/laptop'
    to='test79@%s/oldhag'>
  <show>xa</show>
  <status>gone where the goblins go</status>
</presence>
        """ % (HOSTNAME, )

        self.palaver_xs.dataReceived(JOIN_STATUS_XML)
                
        return self.doWait(_cbJoin1, 5)

    def test81(self): 
        """ Test Section 8.1 http://www.xmpp.org/extensions/xep-0045.html#subject-mod """

        def _cbInvite(t):
            
            mtest  = filter(lambda el: xpath.matches("/message", el), self.wstream.entity.children)
            
            self.failUnless(len(mtest)==2,'Did not get the correct number of messages')

            user1  = filter(lambda el: xpath.matches("/message[@to='wiccarocks@shakespeare.lit/laptop']/subject", el), mtest)
            self.failUnless(len(user1)==1,'Did not get the correct number of messages')

            user2  = filter(lambda el: xpath.matches("/message[@to='79@shakespeare.lit/laptop']/subject[text()='This is a test of the palaver broadcast system.']", el), mtest)

            self.failUnless(len(user2)==1,'Did not get the correct number of messages')

            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
                
        
        def _cbJoin(t):
            ptest  = filter(lambda el: xpath.matches("/presence", el), self.wstream.entity.children)
            self.failUnless(len(ptest)>1, 'Invalid number of presence stanzas')
            
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
                        
            MESSAGE_XML = """
<message
    from='wiccarocks@shakespeare.lit/laptop'
    to='test81@%s' type='groupchat'>
  <x xmlns='http://jabber.org/protocol/muc#user' />
  <subject>This is a test of the palaver broadcast system.</subject>
</message>
""" % (HOSTNAME, )

            self.palaver_xs.dataReceived(MESSAGE_XML)

            return self.doWait(_cbInvite, 3)

        def _cbJoin1(t):
            
            JOIN_STATUS_XML = """
<presence
    from='79@shakespeare.lit/laptop'
    to='test81@%s/79'>
</presence>
            """ % (HOSTNAME,  )

            self.palaver_xs.dataReceived(JOIN_STATUS_XML)
                
            return self.doWait(_cbJoin, 5)

                            
                    
        JOIN_STATUS_XML = """
<presence
    from='wiccarocks@shakespeare.lit/laptop'
    to='test81@%s/oldhag'>
  <show>xa</show>
  <status>gone where the goblins go</status>
</presence>
        """ % (HOSTNAME, )

        self.palaver_xs.dataReceived(JOIN_STATUS_XML)
                
        return self.doWait(_cbJoin1, 5)

    def testKickMessage(self):
        """ Test if user can still chat after kicking                                   ."""

        def _checkError(t):
            test_elem = self.wstream.entity.children.pop()
            self.assertEquals(test_elem['type'],'error')

            self.failUnless(getattr(test_elem.error,'not-authorized',False),
                            'Bad error result')

        def _cbTestKick(t):
            test_elem = self.wstream.entity.children.pop()
            self.assertEquals(test_elem['type'],'result')
            
            test_elem = self.wstream.entity.children.pop()
            self.failUnless(test_elem.hasAttribute('type'),
                            'Presence does not have a type attribute')
            self.assertEquals(test_elem['type'],'unavailable')
            
            for c in test_elem.elements():
                if c.name == 'x' and c.uri == 'http://jabber.org/protocol/muc#user':
                    self.assertEquals(c.item['affiliation'],'none')
                    self.assertEquals(c.item['role'],'none')

            test_elem = self.wstream.entity.children.pop()
            self.failUnless(test_elem.hasAttribute('type'),
                            'Presence does not have a type attribute')
            self.assertEquals(test_elem['type'],'unavailable')
            
            for c in test_elem.elements():
                if c.name == 'x' and c.uri == 'http://jabber.org/protocol/muc#user':
                    self.assertEquals(c.item['affiliation'],'none')
                    self.assertEquals(c.item['role'],'none')
                    
            # send messages 
            MESSAGE_XML = """
<message xmlns='jabber:client' to='testkick@%s' from='earlofcambridge@shakespeare.lit/throne' type='groupchat'>
  <body>3</body>
  </message>
        """ % (HOSTNAME, )

            self.palaver_xs.dataReceived(MESSAGE_XML)
        
            return self.doWait(_checkError, 2)

        def _kick(t):
            for i in range(0, 3):
                test_elem = self.wstream.entity.children.pop()
                self.assertEquals(test_elem.name, 'presence')
        
            BAN_XML = """<iq from='kinghenryv@shakespeare.lit/throne'
    id='ban1'
    to='testkick@%s'
    type='set'>
  <query xmlns='http://jabber.org/protocol/muc#admin'>
    <item role='none'
          jid='earlofcambridge@shakespeare.lit'>
      <reason>Treason</reason>
    </item>
  </query>
</iq>""" % (HOSTNAME,)

            self.palaver_xs.dataReceived(BAN_XML)
            return self.doWait(_cbTestKick, 4)

        
        def _create(t):
            test_elem = self.wstream.entity.children.pop()
            frm = 'testkick@%s/king' % HOSTNAME
            self._testCreate(test_elem, frm)

            PRESENCE_XML = """
    <presence
    from='earlofcambridge@shakespeare.lit/throne'
    to='testkick@%s/kingoftown' />
    """ % (HOSTNAME, )

            self.palaver_xs.dataReceived(PRESENCE_XML)
            return self.doWait(_kick, 3)


        PRESENCE_XML = """
<presence
    from='kinghenryv@shakespeare.lit/throne'
    to='testkick@%s/king' />
    """ % (HOSTNAME, )

        self.palaver_xs.dataReceived(PRESENCE_XML)
        
        return self.doWait(_create, 2)
    
        
    def test91(self):
        """ Test section 9.1 http://www.xmpp.org/extensions/xep-0045.html#ban """

        def _checkDestroy(r):
            miq  = filter(lambda el: xpath.matches("/iq[@type='result']" , el), self.wstream.entity.children)
            
            self.failUnless(len(miq)==1, 'Did not get a destroy result')

            
        def _checkPresenceError(t):
            test_elem = self.wstream.entity.children.pop()
            self.failUnless(xpath.matches("/presence[@type='error']/error", test_elem), 'Presence needs to be an error')
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
            ADMIN_XML = """<iq from='kinghenryv@shakespeare.lit/throne'
    id='admin1'
    to='southhampton@%s'
    type='set'>
  <query xmlns='http://jabber.org/protocol/muc#admin'>
    <destroy jid='southhampton@%s'>
      <reason>Macbeth doth come.</reason>
    </destroy>
  </query>
</iq>""" % (HOSTNAME, HOSTNAME)
            
            self.palaver_xs.dataReceived(ADMIN_XML)
            return self.doWait(_checkDestroy, 2)

        def _checkMessageError(t):
            test_elem = self.wstream.entity.children.pop()
            self.failUnless(xpath.matches("/message[@type='error']/error[@code='403']", test_elem), 'Message needs to be an error')
            # test message error code
            
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
            PRESENCE_XML = """
            <presence
            from='earlofcambridge@shakespeare.lit/throne'
            to='southhampton@%s/kingoftown' />
            """ % (HOSTNAME, )

            self.palaver_xs.dataReceived(PRESENCE_XML)
            return self.doWait(_checkPresenceError, 3)

        
        def _cb91(t):
            test_elem = self.wstream.entity.children.pop()
            self.assertEquals(test_elem['type'],'result')
        
            test_elem = self.wstream.entity.children.pop()
            self.assertEquals(test_elem['type'],'unavailable')
            
            for c in test_elem.elements():
                if c.name == 'x' and c.uri == 'http://jabber.org/protocol/muc#user':
                    self.assertEquals(c.item['affiliation'],'outcast')
                    self.assertEquals(c.item['role'],'none')
                    self.assertEquals(str(c.item.reason),'Treason')
                    self.assertEquals(c.status['code'],'301')

            # test if we can send a message after the ban
            MESSAGE_XML = """
<message xmlns='jabber:client' to='southhampton@%s' from='earlofcambridge@shakespeare.lit/throne' type='groupchat'>
  <body>3</body>
  </message>
        """ % (HOSTNAME, )

            self.palaver_xs.dataReceived(MESSAGE_XML)
            
            return self.doWait(_checkMessageError, 3)
        
        def _ban(t):
            for i in range(0, 3):
                test_elem = self.wstream.entity.children.pop()
                self.assertEquals(test_elem.name, 'presence')
        
            BAN_XML = """<iq from='kinghenryv@shakespeare.lit/throne'
    id='ban1'
    to='southhampton@%s'
    type='set'>
  <query xmlns='http://jabber.org/protocol/muc#admin'>
    <item affiliation='outcast'
          jid='earlofcambridge@shakespeare.lit/throne'>
      <reason>Treason</reason>
    </item>
  </query>
</iq>""" % (HOSTNAME,)

            self.palaver_xs.dataReceived(BAN_XML)
            return self.doWait(_cb91, 2)

        
        def _create(t):
            test_elem = self.wstream.entity.children.pop()
            frm = 'southhampton@%s/king' % HOSTNAME
            self._testCreate(test_elem, frm)

            PRESENCE_XML = """
    <presence
    from='earlofcambridge@shakespeare.lit/throne'
    to='southhampton@%s/kingoftown' />
    """ % (HOSTNAME, )

            self.palaver_xs.dataReceived(PRESENCE_XML)
            return self.doWait(_ban, 3)


        PRESENCE_XML = """
<presence
    from='kinghenryv@shakespeare.lit/throne'
    to='southhampton@%s/king' />
    """ % (HOSTNAME, )

        self.palaver_xs.dataReceived(PRESENCE_XML)
        
        return self.doWait(_create, 2)


        
                

    def testE100ToE103(self):
        """ Test section 9.2 http://www.xmpp.org/extensions/xep-0045.html#modifyban ....."""

        def _removeNoneParticipant(t):
            test_elem = self.wstream.entity.children.pop()
            self.assertEquals(jid.internJID(test_elem['from']).userhost(),'southhampton@%s' % (HOSTNAME,))
            self.assertEquals(test_elem['type'],'result')
            self.assertEquals(test_elem['id'],'removeban4')

        def _checkRemove(t):
            test_elem = self.wstream.entity.children.pop()
            
            self.assertEquals(jid.internJID(test_elem['from']).userhost(),'southhampton@%s' % (HOSTNAME,))
            self.assertEquals(test_elem['type'],'result')

            test_elem = self.wstream.entity.children.pop()

            REMOVE_XML = """
            <iq from='kinghenryv@shakespeare.lit/throne'
    id='removeban4'
    to='southhampton@%s'
    type='set'>
  <query xmlns='http://jabber.org/protocol/muc#admin'>
    <item affiliation='none'
          jid='lordscroop@shakespeare.lit' />
    </query>
</iq>
            """ % (HOSTNAME, )

            self.palaver_xs.dataReceived(REMOVE_XML)

            return self.doWait(_removeNoneParticipant, 3)

        def _remove(t):
            miq  = filter(lambda el: xpath.matches("/iq[@type='result']" , el), self.wstream.entity.children)
            
            self.failUnless(len(miq)==1, 'Did not get a result')

            self.assertEquals(jid.internJID(miq[0]['from']).userhost(),'southhampton@%s' % (HOSTNAME,))
            self.assertEquals(miq[0]['type'],'result')

            # pop the rest
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
            REMOVE_XML = """
            <iq from='kinghenryv@shakespeare.lit/throne'
    id='removeban3'
    to='southhampton@%s'
    type='set'>
  <query xmlns='http://jabber.org/protocol/muc#admin'>
    <item affiliation='none'
          jid='earlofcambridge@shakespeare.lit' />
    </query>
</iq>
            """ % (HOSTNAME, )

            self.palaver_xs.dataReceived(REMOVE_XML)

            return self.doWait(_checkRemove, 3)

        def _modify(t):
            miq  = filter(lambda el: xpath.matches("/iq[@type='result']/query/item[@affiliation='outcast']" % (), el), self.wstream.entity.children)
            
            self.failUnless(len(miq)==1, 'Did not get the correct outcast result')
            
            self.assertEquals(jid.internJID(miq[0]['from']).userhost(),'southhampton@%s' % (HOSTNAME,))
            self.failUnless(miq[0].hasAttribute('type'), 'Wrong Attribute Type')
            self.assertEquals(miq[0]['type'],'result')
            self.assertEquals(miq[0].query.item['affiliation'],'outcast')
            self.assertEquals(miq[0].query.item['jid'],'earlofcambridge@shakespeare.lit')
            self.failUnless(str(miq[0].query.item.reason)=='Treason',
                            'Reason was not returned')

            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()


            MODIFY_XML = """
            <iq from='kinghenryv@shakespeare.lit/throne'
    id='ban3'
    to='southhampton@%s'
    type='set'>
  <query xmlns='http://jabber.org/protocol/muc#admin'>
    <item affiliation='outcast'
          jid='earlofcambridge@shakespeare.lit'>
      <reason>Treason</reason>
    </item>
    <item affiliation='outcast'>
          jid='lordscroop@shakespeare.lit'>
      <reason>Treason</reason>
    </item>
    <item affiliation='outcast'
          jid='sirthomasgrey@shakespeare.lit'>
      <reason>Treason</reason>
    </item>
  </query>
</iq>
            """ % (HOSTNAME,)

            self.palaver_xs.dataReceived(MODIFY_XML)

            return self.doWait(_remove, 3)

        def _first_ban_result(t):
            
            test_elem = self.wstream.entity.children.pop()
            self.failUnless(xpath.matches("/iq[@type='result']", test_elem), 'Error in ban result.')
            
            GET_XML = """
        <iq from='kinghenryv@shakespeare.lit/throne'
    id='ban2'
    to='southhampton@%s'
    type='get'>
  <query xmlns='http://jabber.org/protocol/muc#admin'>
    <item affiliation='outcast' />
  </query>
</iq>""" % (HOSTNAME,)
            self.palaver_xs.dataReceived(GET_XML)
            
            return self.doWait(_modify, 4)

        def _do_first_ban(t):
            # pop off presence
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
            BAN_XML = """<iq from='kinghenryv@shakespeare.lit/throne'
    id='ban1'
    to='southhampton@%s'
    type='set'>
  <query xmlns='http://jabber.org/protocol/muc#admin'>
    <item affiliation='outcast'
          jid='earlofcambridge@shakespeare.lit'>
      <reason>Treason</reason>
    </item>
  </query>
</iq>""" % (HOSTNAME,)

            self.palaver_xs.dataReceived(BAN_XML)
        
            return self.doWait(_first_ban_result, 4) 
            


        
        PRESENCE_XML = """
    <presence
    from='kinghenryv@shakespeare.lit/throne'
    to='southhampton@%s/king' />
    """ % (HOSTNAME, )

        self.palaver_xs.dataReceived(PRESENCE_XML)
        
        return self.doWait(_do_first_ban, 3)

    def test93(self):
        """ Test section 9.3 http://www.xmpp.org/extensions/xep-0045.html#grantmember ..........."""

        def _testJoin(r):
            self.failUnless(len(self.wstream.entity.children)>1, 'No elements found')
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
                self.failUnless(xpath.matches("/presence[not(@type)]", test_elem), 'Error joining room.')

        def _cb93(t):
            test_elem = self.wstream.entity.children.pop()
            self.failUnless(xpath.matches("/iq[@type='result']/query", test_elem), 'Error in member add result.')
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
            # join after we are made a member
            PRESENCE_XML = """
<presence
    from='hag66@shakespeare.lit/throne'
    to='membertest@%s/ha66' />
    """ % (HOSTNAME, )

            self.palaver_xs.dataReceived(PRESENCE_XML)
            
            return self.doWait(_testJoin, 2)
            
        def _create(t):
            test_elem = self.wstream.entity.children.pop()
            frm = 'membertest@%s/king' % HOSTNAME
            self._testCreate(test_elem, frm)
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
                
            MEMBER_XML = """
            <iq from='kinghenryv@shakespeare.lit/throne'
    id='member1'
    to='membertest@%s'
    type='set'>
            <query xmlns='http://jabber.org/protocol/muc#admin'>
               <item affiliation='member'
                        jid='hag66@shakespeare.lit'/>
            </query>
            </iq>
    """ % (HOSTNAME, )

            self.palaver_xs.dataReceived(MEMBER_XML)
            return self.doWait(_cb93, 3)

        PRESENCE_XML = """
<presence
    from='kinghenryv@shakespeare.lit/throne'
    to='membertest@%s/king' />
    """ % (HOSTNAME, )

        self.palaver_xs.dataReceived(PRESENCE_XML)
        
        return self.doWait(_create, 2)


    def testGrantPlayerMember(self):
        """ Test changing affiliations from player to member """

        def _cbMember(t):
            test_elem = self.wstream.entity.children.pop()
            self.failUnless(xpath.matches("/iq[@type='result']/query", test_elem), 'Error in player add result.')
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
                self.failUnless(xpath.matches("/presence/x/item[@affiliation='member']", test_elem), 'Bad affiliation')
                self.failUnless(xpath.matches("/presence/x/item[@role='participant']", test_elem), 'Bad role')

        def _testJoin(r):
            self.failUnless(len(self.wstream.entity.children)>1, 'No elements found')
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
                self.failUnless(xpath.matches("/presence[not(@type)]", test_elem), 'Error joining room.')
            PLAYER_XML = """
            <iq from='kinghenryv@shakespeare.lit/throne'
    id='player1'
    to='playertest@%s'
    type='set'>
            <query xmlns='http://jabber.org/protocol/muc#admin'>
               <item affiliation='member'
                        jid='hag66@shakespeare.lit'/>
            </query>
            </iq>
    """ % (HOSTNAME, )

            self.palaver_xs.dataReceived(PLAYER_XML)
            return self.doWait(_cbMember, 3)

        def _cbPlayer(t):
            test_elem = self.wstream.entity.children.pop()
            self.failUnless(xpath.matches("/iq[@type='result']/query", test_elem), 'Error in player add result.')
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
            # join after we are made a player
            PRESENCE_XML = """
<presence
    from='hag66@shakespeare.lit/throne'
    to='playertest@%s/ha66' />
    """ % (HOSTNAME, )

            self.palaver_xs.dataReceived(PRESENCE_XML)
            
            return self.doWait(_testJoin, 2)
            
        def _create(t):
            test_elem = self.wstream.entity.children.pop()
            frm = 'playertest@%s/king' % HOSTNAME
            self._testCreate(test_elem, frm)
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
                
            PLAYER_XML = """
            <iq from='kinghenryv@shakespeare.lit/throne'
    id='player1'
    to='playertest@%s'
    type='set'>
            <query xmlns='http://jabber.org/protocol/muc#admin'>
               <item affiliation='player'
                        jid='hag66@shakespeare.lit'/>
            </query>
            </iq>
    """ % (HOSTNAME, )

            self.palaver_xs.dataReceived(PLAYER_XML)
            return self.doWait(_cbPlayer, 3)

        PRESENCE_XML = """
<presence
    from='kinghenryv@shakespeare.lit/throne'
    to='playertest@%s/king' />
    """ % (HOSTNAME, )

        self.palaver_xs.dataReceived(PRESENCE_XML)
        
        return self.doWait(_create, 2)
    
    def test96(self):
        """ Test section 9.6 http://www.xmpp.org/extensions/xep-0045.html#grantmod ..........."""

        def _cb96(t):
            test_elem = self.wstream.entity.children.pop()
            self.failUnless(xpath.matches("/iq[@type='result']/query", test_elem), 'Error in moderator result.')
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
                self.failUnless(xpath.matches("/presence[@from='modtest@%s/witch']/x/item[@role='moderator']" % (HOSTNAME,), test_elem), 'Error in presence.')
                

        def _setRole(t):
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
            MEMBER_XML = """
            <iq from='kinghenryv@shakespeare.lit/throne'
    id='member1'
    to='modtest@%s'
    type='set'>
            <query xmlns='http://jabber.org/protocol/muc#admin'>
               <item role='moderator'
                     nick='witch'/>
            </query>
            </iq>
    """ % (HOSTNAME, )

            self.palaver_xs.dataReceived(MEMBER_XML)
            return self.doWait(_cb96, 3)

        def _create(t):
            test_elem = self.wstream.entity.children.pop()
            frm = 'modtest@%s/king' % HOSTNAME
            self._testCreate(test_elem, frm)
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()

            PRESENCE_XML = """
<presence
    from='hag66@shakespeare.lit/witch'
    to='modtest@%s/witch' />
    """ % (HOSTNAME, )

            self.palaver_xs.dataReceived(PRESENCE_XML)
        
            return self.doWait(_setRole, 2)

        PRESENCE_XML = """
<presence
    from='kinghenryv@shakespeare.lit/throne'
    to='modtest@%s/king' />
    """ % (HOSTNAME, )

        self.palaver_xs.dataReceived(PRESENCE_XML)
        
        return self.doWait(_create, 2)

        

    def test106(self):
        """ Test section 10.6 http://www.xmpp.org/extensions/xep-0045.html#grantadmin ..........."""

        
        def _cb106(t):
            test_elem = self.wstream.entity.children.pop()
            self.assertEquals(test_elem['type'],'result')
        
            test_elem = self.wstream.entity.children.pop()
                        
            for c in test_elem.elements():
                if c.name == 'x' and c.uri == 'http://jabber.org/protocol/muc#user':
                    self.assertEquals(c.item['affiliation'],'admin')
                    self.assertEquals(c.item['role'],'moderator')
                    
                    
        def _admin(t):

            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
                self.assertEquals(test_elem.name, 'presence')
            
            ADMIN_XML = """<iq from='kinghenryv@shakespeare.lit/throne'
    id='admin1'
    to='admintest@%s'
    type='set'>
  <query xmlns='http://jabber.org/protocol/muc#admin'>
    <item affiliation='admin'
          jid='earlofcambridge@shakespeare.lit'/>
  </query>
</iq>""" % (HOSTNAME,)
            
            self.palaver_xs.dataReceived(ADMIN_XML)
            return self.doWait(_cb106, 4)

        
        def _create(t):
            test_elem = self.wstream.entity.children.pop()
            frm = 'admintest@%s/king' % HOSTNAME
            self._testCreate(test_elem, frm)
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
                
            PRESENCE_XML = """
    <presence
    from='earlofcambridge@shakespeare.lit/throne'
    to='admintest@%s/kingoftown' />
    """ % (HOSTNAME, )

            self.palaver_xs.dataReceived(PRESENCE_XML)
            return self.doWait(_admin, 3)


        PRESENCE_XML = """
<presence
    from='kinghenryv@shakespeare.lit/throne'
    to='admintest@%s/king' />
    """ % (HOSTNAME, )

        self.palaver_xs.dataReceived(PRESENCE_XML)
        
        return self.doWait(_create, 2)

    def test109(self):
        """ Test section 10.9 http://www.xmpp.org/extensions/xep-0045.html#destroyroom ..........."""
        
        def _cb109(t):
            ptest  = filter(lambda el: xpath.matches("/presence[@type='unavailable']/x/item[@role='none']", el), self.wstream.entity.children)

            self.failUnless(len(ptest)==1, 'Presence was not sent that use left the room.')

            iqtest  = filter(lambda el: xpath.matches("/iq[@type='result']", el), self.wstream.entity.children)
            
            self.failUnless(len(iqtest)==1, 'Invalid iq result.')

                                
                    
        def _admin(t):

            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
                self.assertEquals(test_elem.name, 'presence')
            
            ADMIN_XML = """<iq from='kinghenryv@shakespeare.lit/throne'
    id='admin1'
    to='destroytest@%s'
    type='set'>
  <query xmlns='http://jabber.org/protocol/muc#admin'>
    <destroy jid='destroytest@%s'>
      <reason>Macbeth doth come.</reason>
    </destroy>
  </query>
</iq>""" % (HOSTNAME, HOSTNAME)
            
            self.palaver_xs.dataReceived(ADMIN_XML)
            return self.doWait(_cb109, 4)


        PRESENCE_XML = """
<presence
    from='kinghenryv@shakespeare.lit/throne'
    to='destroytest@%s/king' />
    """ % (HOSTNAME, )

        self.palaver_xs.dataReceived(PRESENCE_XML)
        
        return self.doWait(_admin, 2)

    def testPresenceLeak(self):
        """ Test to make sure presence does not leak.                                   ."""
        user_list = []
        
        def testLeave(t):
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
                self.assertEquals(test_elem['type'], 'unavailable')
                self.failUnless(test_elem['to'].lower() in user_list)

                user_list.pop(user_list.index(test_elem['to'].lower()))
            # Test for leak, if all users did not get unavailable then there is a leak

            self.failUnless(len(user_list)==0, 'Not all users got unavailable presence %s ' % str(user_list))
            
        def testJoin(t):
            send_one_to_users  = 0
            send_one_to_member = 0
            send_two_to_users  = 0
            send_two_to_member = 0
            
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
                if test_elem.name =='presence' and test_elem['from'] == 'leak@%s/One' % (HOSTNAME,) \
                       and test_elem['to'] != '2@shakespeare.lit/testing':
                    send_one_to_users += 1
                    
                if test_elem.name =='presence' and test_elem['from'] == 'leak@%s/two' % (HOSTNAME,):
                    send_two_to_users += 1
                    if test_elem['to'].lower() not in user_list:
                        user_list.append(test_elem['to'].lower())

            self.failUnless(send_one_to_users >= 2, 'Not enough presence elements')
            #self.assertEquals(send_one_to_users, 5)
            
            self.failUnless(send_two_to_users >= 3, 'Not enough presence elements')
            #self.assertEquals(send_two_to_users, 6)
            
            PRESENCE_XML = """
            <presence from='one@shakespeare.lit/testing'  to='leak@%s/one' type='unavailable'/>
            """ % (HOSTNAME, )

            self.palaver_xs.dataReceived(PRESENCE_XML)
        
            return self.doWait(testLeave, 7)

        def testLeak(t):
            PRESENCE_XML = """
    <presence from='One@shakespeare.lit/testing'  to='leak@%s/One' />
    <presence from='2@shakespeare.lit/testing' to='leak@%s/two' />
    """ % (HOSTNAME, HOSTNAME)

            self.palaver_xs.dataReceived(PRESENCE_XML)
        
            return self.doWait(testJoin, 16)
        
        self._createRoom('hag66@shakespeare.lit/pda', 'leak@%s/thirdwitch' % (HOSTNAME, ))
        return self.doWait(testLeak, 3)
    

    def testPresenceRaceCondition(self):
        """
        This is a test for a race condition when someone leaves the room immediatly after they join.
        """
        def testJoin(t):
            unavailable = False
            test_elem = self.wstream.entity.children.pop()
            if test_elem.name == 'presence' and \
                   test_elem.hasAttribute('type') and \
                   test_elem['type'] == 'unavailable':
                unavailable = True
            self.failUnless(unavailable,'Did NOT leave the room')
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
                
        def testRace(t):    
            PRESENCE_XML = """
    <presence from='race@shakespeare.lit/testing'  to='racetest@%s/RaceTest' />
    <presence from='race@shakespeare.lit/testing' type='unavailable' to='racetest@%s/RaceTest' />
    """ % (HOSTNAME, HOSTNAME)

            self.palaver_xs.dataReceived(PRESENCE_XML)
            
            return self.doWait(testJoin, 18)

        self._createRoom('hag66@shakespeare.lit/pda', 'racetest@%s/thirdwitch' % (HOSTNAME, ))
        return self.doWait(testRace, 3)


    def testPresenceMessageRaceCondition(self):
        """
        This is a test for a race condition when someone joins and sends a message right after.
        """
        def testJoin(t):
            test_elem = self.wstream.entity.children.pop()
            self.failUnless(xpath.matches("/message[@type='groupchat']/body", test_elem), 'Wrong message type')
            test_elem = self.wstream.entity.children.pop()
            self.failUnless(xpath.matches("/message[@type='groupchat']/body", test_elem), 'Wrong message type')
            
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
                
        def testRace(t):    
            PRESENCE_XML = """
            <presence xmlns='jabber:client' to='messagerace@%s/ani011010ani@chesspark.com' from='ani011010ani@chesspark.com/cpc'>
            <x xmlns='http://jabber.org/protocol/muc'/>
            </presence>
            <message xmlns='jabber:client' to='messagerace@%s' type='groupchat' from='ani011010ani@chesspark.com/cpc'>
            <body>hello</body>
            <x xmlns='jabber:x:event'>
            <composing/></x>
            </message>
    """ % (HOSTNAME, HOSTNAME)

            self.palaver_xs.dataReceived(PRESENCE_XML)
            
            return self.doWait(testJoin, 18)

        self._createRoom('hag66@shakespeare.lit/pda', 'messagerace@%s/thirdwitch' % (HOSTNAME, ))
        return self.doWait(testRace, 3)


    def testDoublePresence(self):
        """
        This is a test for a race condition when someone leaves the room immediatly after they join.
        """

        def finish(t):
            pass
        
        def testJoin(t):

            test_elem = self.wstream.entity.children.pop()
            self.failUnless(test_elem.name == 'presence', 'not a presence element')
            self.failUnless(not test_elem.hasAttribute('type'), 'not a join presence stanza')
            
            self.failUnless(len(self.wstream.entity.children)<=5, 'too many elements %s' % str(len(self.wstream.entity.children)))

            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()

            PRESENCE_XML = """
             <presence xmlns='jabber:client' to='doublepresence@%s/thepug' from='nathan.zorn@gmail.com/Work7E48776A' type='unavailable' />
             """ % (HOSTNAME, )

            self.palaver_xs.dataReceived(PRESENCE_XML)

            return self.doWait(finish, 3)
            
            
        def testRace(t):
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
            PRESENCE_XML = """
             <presence xmlns='jabber:client' to='doublepresence@%s/thepug' from='nathan.zorn@gmail.com/Work7E48776A'>
             <priority>1</priority>
             <c xmlns='http://jabber.org/protocol/caps' node='http://gaim.sf.net/caps' ver='2.0.0beta6'/>
             <x xmlns='http://jabber.org/protocol/muc'/><x xmlns='vcard-temp:x:update'/>
             </presence>
             <presence xmlns='jabber:client' to='doublepresence@%s/thepug' from='nathan.zorn@gmail.com/Work7E48776A'>
             <priority>1</priority>
             <c xmlns='http://jabber.org/protocol/caps' node='http://gaim.sf.net/caps' ver='2.0.0beta6'/>
             <x xmlns='http://jabber.org/protocol/muc'/>
             <x xmlns='vcard-temp:x:update'/>
             </presence>
    """ % (HOSTNAME, HOSTNAME)

            self.palaver_xs.dataReceived(PRESENCE_XML)
            
            return self.doWait(testJoin, 18)

        self._createRoom('hag66@shakespeare.lit/pda', 'doublepresence@%s/thirdwitch' % (HOSTNAME, ))
        return self.doWait(testRace, 3)

        

    def testResourceAdminIssue(self):
        """
        If a user is set as an admin with a resource it creates issues.

        """

        def cbGetAdmin(t):
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
                self.failUnless(test_elem['type']!='error', 'We got an error on iq return')


        def testGetAdmin(t):
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
            MEMBER_XML = """
            <iq from='admintest@testing.com/ha'
    id='member1'
    to='admin@%s'
    type='get'>
            <query xmlns='http://jabber.org/protocol/muc#admin' />
            </iq>
    """ % (HOSTNAME, )

            self.palaver_xs.dataReceived(MEMBER_XML)
            return self.doWait(cbGetAdmin, 3)    


        def testSetAdmin(t):
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
            MEMBER_XML = """
            <iq from='adminresource@shakespeare.lit/throne'
    id='member1'
    to='admin@%s'
    type='set'>
            <query xmlns='http://jabber.org/protocol/muc#admin'>
               <item affiliation='owner'  jid='admintest@testing.com/ha'/>
            </query>
            </iq>
    """ % (HOSTNAME, )

            self.palaver_xs.dataReceived(MEMBER_XML)
            return self.doWait(testGetAdmin, 3)    

        self._createRoom('adminresource@shakespeare.lit/test', 'admin@%s/thirdwitch' % (HOSTNAME, ))
        return self.doWait(testSetAdmin, 3)


    def testResourceMemberAdminIssue(self):
        """
        If a user is set as an admin with a resource it creates issues.

        """

        def cbGetAdmin(t):
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
                self.failUnless(test_elem['type']!='error', 'We got an error on iq return')


        def testGetAdmin(t):
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
            MEMBER_XML = """
            <iq from='admintest@testing.com/ha'
    id='member1'
    to='admin@%s'
    type='get'>
            <query xmlns='http://jabber.org/protocol/muc#admin' />
            </iq>
    """ % (HOSTNAME, )

            self.palaver_xs.dataReceived(MEMBER_XML)
            return self.doWait(cbGetAdmin, 3)    


        def testSetAdmin(t):
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
            MEMBER_XML = """
            <iq from='adminresource@shakespeare.lit/throne'
    id='member1'
    to='admin@%s'
    type='set'>
            <query xmlns='http://jabber.org/protocol/muc#admin'>
               <item affiliation='owner'  jid='admintest@testing.com/ha'/>
            </query>
            </iq>
    """ % (HOSTNAME, )

            self.palaver_xs.dataReceived(MEMBER_XML)
            return self.doWait(testGetAdmin, 3)    


        def testSetMember(t):
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
            MEMBER_XML = """
            <iq from='adminresource@shakespeare.lit/throne'
    id='member1'
    to='admin@%s'
    type='set'>
            <query xmlns='http://jabber.org/protocol/muc#admin'>
               <item affiliation='member'  jid='admintest@testing.com'/>
            </query>
            </iq>
    """ % (HOSTNAME, )

            self.palaver_xs.dataReceived(MEMBER_XML)
            return self.doWait(testSetAdmin, 3)    

        self._createRoom('adminresource@shakespeare.lit/test', 'admin@%s/thirdwitch' % (HOSTNAME, ))
        return self.doWait(testSetMember, 3)


    def testRoomAttributeQuery(self):
        """ Test number of sets in cache for Room Attributes . Also number of selects. """
        
        self.failUnless(self.groupchat_service.storage.resetCache())

        def cbComponent(t):
            test_elem = self.wstream.entity.children.pop()
            self.assertNotEquals(test_elem['type'],'error')
            # test for correct namespace
            self.assertEquals(test_elem.query.uri,'http://jabber.org/protocol/disco#items')

            self.failUnless(self.groupchat_service.storage.test_hidden_cache_sets==1, 
                            'Wrong cache set count')
            self.failUnless(self.groupchat_service.storage.test_attributelist_cache_sets==1, 
                            'Wrong attribute cache set count')

        def cbDisco(t):
            test_elem = self.wstream.entity.children.pop()
            
            self.assertNotEquals(test_elem['type'],'error')
            # test for correct namespace
            self.assertEquals(test_elem.query.uri,'http://jabber.org/protocol/disco#info')
            
            self.failUnless(self.groupchat_service.storage.test_attributelist_cache_sets==1, 
                            'Wrong cache set count')

            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()

            CLIENT_XML = """
           <iq from='hag66@shakespeare.lit/pda' xmlns='jabber:client'
           id='disco1'
           to='%s'
           type='get'>
           <query xmlns='http://jabber.org/protocol/disco#items'/>
           </iq>
        """ % (HOSTNAME)

            self.palaver_xs.dataReceived(CLIENT_XML)

            return self.doWait(cbComponent, 2)        

        def cbCreate(t):
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()

            CLIENT_XML = """
           <iq from='hag66@shakespeare.lit/pda' xmlns='jabber:client'
           id='disco3'
           to='darkcave@%s'
           type='get'>
           <query xmlns='http://jabber.org/protocol/disco#info'/>
           </iq>
        """ % (HOSTNAME)

            self.palaver_xs.dataReceived(CLIENT_XML)


            return self.doWait(cbDisco, 2)        


        self._createRoom('hag66@shakespeare.lit/pda', 'darkcave@%s/thirdwitch' % (HOSTNAME, ))

        return self.doWait(cbCreate, 2)

    def testZDisconnect(self):
        """ Test Disconnect ............................................................."""
        self.palaver_xs.connectionLost(None)
        
    
    def tearDown(self):
        # self.room_service.delayed_queue_call.stop()
        pending = reactor.getDelayedCalls()
        if pending:
            for p in pending:
                if p.active():
                    p.cancel()

        
    def tearDownClass(self):
        for root, dirs, files in os.walk('/tmp/palaver_test/'):
            for f in files:
                os.unlink(root+f)
            
        os.rmdir('/tmp/palaver_test/')
    



class StorageTests(unittest.TestCase):
    pass
