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



#import twisted
#twisted.internet.base.DelayedCall.debug = True    

class XEP045Tests(unittest.TestCase):
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
        sadmins = ['server@serveradmin.com']
        # allow for other storage in tests
        st = dir_storage.Storage(spool='/tmp/palaver_test/')
        st.sadmins = sadmins        
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
        
        
        # now trigger authd event
        self.palaver_xs.dispatch(self.palaver_xs, xmlstream.STREAM_AUTHD_EVENT)
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
        

    def _clearElems(self):
        while len(self.wstream.entity.children)>1:
            test_elem = self.wstream.entity.children.pop()

    def doWait(self, cb, num, timeout=5):
        d = defer.Deferred()
        self._waitForData(num,d, timeout)
        d.addCallback(cb)
        return d

    def _createRoom(self, frm, to):
        CLIENT_XML = """<presence from='%s' to='%s'/>""" % (frm, to, )        
        self.palaver_xs.dataReceived(CLIENT_XML)
    
    def test1stCreateRoom(self):
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


    def testLeaveAndDeleteRoom(self):
        """ Test leave and delete a room .........................................................."""

        def test109(t):
            test_elem = self.wstream.entity.children.pop()
            self.failUnless(xpath.matches("/presence/x/status[@code='201']", test_elem), 'Invalid room create.')
            

        def testRoom(t):
            self._clearElems()
            # join the room again and see if we get the status code
            CLIENT_XML = """<presence from='%s' to='%s'>
    <x xmlns='http://jabber.org/protocol/muc'/>
 </presence>""" % ('hag66@shakespeare.lit/pda', 'delete@%s/thirdwitch' % (HOSTNAME, ))        
            self.palaver_xs.dataReceived(CLIENT_XML)
            return self.doWait(test109, 2)
    
        def leaveRoom(t):
            test_elem = self.wstream.entity.children.pop()
            self.failUnless(xpath.matches("/iq[@type='result']", test_elem), 'Invalid iq result.')
            self._clearElems()

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

    

    def testUnicodeMessages(self):
        """ Test send strange chars to room ......................................................"""


        def testRoom(t):
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
                self.failUnless(test_elem.name == 'message', 'Not a message returned.')
                self.failUnless(test_elem['type'] == 'groupchat', 'Error in message type')
                
    
        def _cbCreateRoom(t):
            self.assertEquals(t, True)
            test_elem = self.wstream.entity.children.pop()
                        
            frm = 'unicode@%s/thirdwitch' % HOSTNAME
            self._testCreate(test_elem, frm)

            MESSAGE_XML = """<message from='hag66@shakespeare.lit/pda' to='unicode@%s' type='groupchat' id='2822'>
<body>ä ö and ü  %%</body>
</message> """ % (HOSTNAME,)

            self.palaver_xs.dataReceived(MESSAGE_XML)
            return self.doWait(testRoom, 2)
            
                
        CLIENT_XML = """<presence from='%s' to='%s' />""" % ('hag66@shakespeare.lit/pda', 'unicode@%s/thirdwitch' % (HOSTNAME, ))        
        self.palaver_xs.dataReceived(CLIENT_XML)
        return self.doWait(_cbCreateRoom, 2)


    def testNameSpaceMessages(self):
        """ Test send strange chars to room ......................................................"""


        def testRoom(t):
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
                self.failUnless(test_elem.body.uri==test_elem.uri, 'uri is wrong')
                self.failUnless(test_elem.name == 'message', 'Not a message returned.')
                self.failUnless(test_elem['type'] == 'groupchat', 'Error in message type')
                
    
        def _cbCreateRoom(t):
            self.assertEquals(t, True)
            test_elem = self.wstream.entity.children.pop()
                        
            frm = 'unicode@%s/thirdwitch' % HOSTNAME
            self._testCreate(test_elem, frm)

            MESSAGE_XML = """<message from='hag66@shakespeare.lit/pda' to='unicode@%s' type='groupchat' id='2822'>
<body>yes, i know you do </body>
<nick xmlns="http://jabber.org/protocol/nick">cgrady</nick>
</message> """ % (HOSTNAME,)

            self.palaver_xs.dataReceived(MESSAGE_XML)
            return self.doWait(testRoom, 2)
            
                
        CLIENT_XML = """<presence from='%s' to='%s' />""" % ('hag66@shakespeare.lit/pda', 'unicode@%s/thirdwitch' % (HOSTNAME, ))        
        self.palaver_xs.dataReceived(CLIENT_XML)
        return self.doWait(_cbCreateRoom, 2)

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
            
        def _doTest(t):            
            PRESENCE_XML = """
<presence
    from='palaver@shakespeare.lit/pda'
    to='darkcave@%s/change_nick'/>
        """ % (HOSTNAME,)

            self.palaver_xs.dataReceived(PRESENCE_XML)
        
            return self.doWait(_cbJoin, 2)

        PRESENCE_XML = """
<presence
    from='testingp@shakespeare.lit/pda'
    to='darkcave@%s/testingtesting'/>
        """ % (HOSTNAME,)
        
        self.palaver_xs.dataReceived(PRESENCE_XML)
        
        return self.doWait(_doTest, 2)
    
    
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


    def test75BadInvite(self): 
        """ Test Section 7.5 http://www.xmpp.org/extensions/xep-0045.html#invite ...."""

        def _cbInvite(t):
            child_count = len(self.wstream.entity.children)
            
            test_elem = self.wstream.entity.children.pop()
                
            self.failUnless(test_elem.name=='message',
                            'Not a message returned')
            self.failUnless(test_elem['type']=='error',
                            'Need an error here.')
        
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
    <invite to='@shakespeare.lit'>
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
    to='test79@%s' type='groupchat'>
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
            self.failUnless(xpath.matches("/message[@type='error']/error", test_elem), 'Message needs to be an error')
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
          jid='earlofcambridge@shakespeare.lit'>
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

        def _cb93(t):
            test_elem = self.wstream.entity.children.pop()
            self.failUnless(xpath.matches("/iq[@type='result']/query", test_elem), 'Error in member add result.')
            
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

            self.failUnless(len(user_list)==0, 'Not all users got unavailable presence')
            
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

        
    def testZDisconnect(self):
        """ Test Disconnect ............................................................."""
        self.palaver_xs.connectionLost(None)
        
    
    def tearDown(self):
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
    

    def testServerAdminJoiningPrivateRoom(self):
        """ Test Server Admin joining a private room .................."""

        def test109(t):
            test_elem = self.wstream.entity.children.pop()
            self.failUnless(xpath.matches("/presence/x/item[@jid='hag66@shakespeare.lit/pda']", test_elem), 'Invalid room join.')
            

        def testRoom(t):
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()
            # join the room again and see if we get the status code
            CLIENT_XML = """<presence from='%s' to='%s'>
    <x xmlns='http://jabber.org/protocol/muc'/>
 </presence>""" % ('hag66@shakespeare.lit/pda', 'hidden@%s/thirdwitch' % (HOSTNAME, ))        
            self.palaver_xs.dataReceived(CLIENT_XML)
            return self.doWait(test109, 2)
    
        def joinRoom(t):
            test_elem = self.wstream.entity.children.pop()
            self.failUnless(xpath.matches("/iq[@type='result']", test_elem), 'Invalid iq result.')
            while len(self.wstream.entity.children)>1:
                test_elem = self.wstream.entity.children.pop()

            CLIENT_XML = """<presence from='%s' to='%s' >
    <x xmlns='http://jabber.org/protocol/muc'/>
 </presence>""" % ('server@serveradmin.com/pda', 'hidden@%s/thirdwitch' % (HOSTNAME, ))        


            self.palaver_xs.dataReceived(CLIENT_XML)
            return self.doWait(testRoom, 2)
            

        def _cbCreateRoom(t):
            self.assertEquals(t, True)
            test_elem = self.wstream.entity.children.pop()
                        
            frm = 'hidden@%s/thirdwitch' % HOSTNAME
            self._testCreate(test_elem, frm)

            # send config
            CONFIG_XML = """<iq from='hag66@shakespeare.lit/pda' id='arbiter_kds_9877' type='set' to='hidden@%s'>
            <query xmlns='http://jabber.org/protocol/muc#admin'>
             <x xmlns='jabber:x:data' type='submit'>
              <field var='FORM_TYPE'>
                <value>http://jabber.org/protocol/muc#roomconfig</value>
              </field>
               <field var='muc#roomconfig_whois'>
                   <value>anyone</value>
               </field>
              <field var="muc#roomconfig_publicroom" type="boolean" label="Turn on public searching of room? Make it public.">
                <value>0</value>
              </field>
             </x></query></iq>""" % (HOSTNAME, )
            self.palaver_xs.dataReceived(CONFIG_XML)
            return self.doWait(joinRoom, 2)
            

        CLIENT_XML = """<presence from='%s' to='%s'>
    <x xmlns='http://jabber.org/protocol/muc'/>
 </presence>""" % ('hag66@shakespeare.lit/pda', 'hidden@%s/thirdwitch' % (HOSTNAME, ))        
        self.palaver_xs.dataReceived(CLIENT_XML)
        return self.doWait(_cbCreateRoom, 2)        


    def testAffiliateChangeAndExitRaceCondition(self):
        """
        This is a test for a race condition when an affiliation changes immediately before a user leaves.
        """

        def _cbModify(t):
            found_unavailable = 0
            found_iq_result   = False
            # The last element in the children list is the last one received. 
            # The first elements we see should be unavailable
            while len(self.wstream.entity.children) > 0:
                test_elem = self.wstream.entity.children.pop()
                if test_elem.name == 'presence' \
                        and 'type' in test_elem.attributes \
                        and test_elem['type'] == 'unavailable':
                    found_unavailable += 1
                elif test_elem.name == 'presence' and found_unavailable < 3:
                    self.fail('The affiliation change needs to happen before the user leaves the room. %s' % (test_elem.toXml()))

                if test_elem.name == 'iq':
                    found_iq_result = True

            self.failUnless(found_iq_result, 'Did not change affiliation')
            # we should check order


        def modifyAndLeave(t):
            while len(self.wstream.entity.children) > 0:
                test_elem = self.wstream.entity.children.pop()
            MODIFY_XML = """
              <iq from='mercutio@shakespeare.lit' to='affiliation@%(host)s' type='set' id='arbiter_llh_142560'>
                <query xmlns='http://jabber.org/protocol/muc#admin'>
                  <item affiliation='member' jid='juliet@shakespeare.lit' role='visitor'/>
                </query>
              </iq>
              <iq from='mercutio@shakespeare.lit' to='affiliation@%(host)s' type='set' id='arbiter_rzp_142561'>
                <query xmlns='http://jabber.org/protocol/muc#admin'>
                  <item affiliation='member' jid='romeo@shakespeare.lit' role='visitor'/>
                </query>
              </iq>
              <presence from='juliet@shakespeare.lit/pda' to='affiliation@%(host)s/juliet' type='unavailable'/>
              <presence from='romeo@shakespeare.lit/pda' to='affiliation@%(host)s/romeo' type='unavailable'/>
            """ % {'host': HOSTNAME}

            self.palaver_xs.dataReceived(MODIFY_XML)
            return self.doWait(_cbModify, 10)


        def sendJoin(t):
            while len(self.wstream.entity.children) > 0:
                test_elem = self.wstream.entity.children.pop()
            PRESENCE_XML = """
              <presence
                  from='romeo@shakespeare.lit/pda'
                  to='affiliation@%(host)s/romeo'/>
              <presence
                  from='juliet@shakespeare.lit/pda'
                  to='affiliation@%(host)s/juliet'/>
            """ % {'host': HOSTNAME}

            self.palaver_xs.dataReceived(PRESENCE_XML)
            return self.doWait(modifyAndLeave, 4)


        PRESENCE_XML = """
          <presence
              from='mercutio@shakespeare.lit/pda'
              to='affiliation@%(host)s/mercutio'/>
        """ % {'host': HOSTNAME}

        self.palaver_xs.dataReceived(PRESENCE_XML)
        return self.doWait(sendJoin, 2)


    def testCapsAndEncodedNames(self):
        """
        test case bugs and spaces in rooms
        """
        def _discoItems(t):
            pass


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
            room = "inner\\20chamber@" + HOSTNAME

            CLIENT_XML = """
           <iq from='hag66@shakespeare.lit/pda' xmlns='jabber:client'
           id='disco1'
           to='%s'
           type='get'>
           <query xmlns='http://jabber.org/protocol/disco#items'/>
           </iq>
        """ % (room)


            self.palaver_xs.dataReceived(CLIENT_XML)

            return self.doWait(_discoItems, 2)

        def _cbCreateRoom(t):
            self.assertEquals(t, True)
            test_elem = self.wstream.entity.children.pop()
                        
            #frm = 'WuZisk@chesspark.com/cpc'
            room = "inner\\20chamber@" + HOSTNAME
            frm = room+"/wuzisk@wuchess.com"
            self._testCreate(test_elem, frm)


            CLIENT_XML = """
           <iq from='hag66@shakespeare.lit/pda' xmlns='jabber:client'
           id='disco1'
           to='%s'
           type='get'>
           <query xmlns='http://jabber.org/protocol/disco#info'/>
           </iq>
        """ % (room)


            self.palaver_xs.dataReceived(CLIENT_XML)

            return self.doWait(_cb61, 2)




        CLIENT_XML = """<presence xmlns='jabber:client' to='Inner\\20Chamber@%s/wuzisk@wuchess.com' from='WuZisk@wuchess.com/cpc'><x xmlns='http://jabber.org/protocol/muc'/></presence>""" % (HOSTNAME,)
        
        self.palaver_xs.dataReceived(CLIENT_XML)
        return self.doWait(_cbCreateRoom, 2)        
