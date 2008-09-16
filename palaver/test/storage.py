# Copyright (c) 2005 - 2007 Christopher Zorn, OGG, LLC 
# See LICENSE.txt for details
import os
import sys
from twisted.trial import unittest
from twisted.enterprise import adbapi
from twisted.words.protocols.jabber import jid
from twisted.internet import defer
from twisted.words.xish import domish

from palaver import storage
from palaver import pgsql_storage
from palaver import dir_storage, memory_storage


TESTROOM0  = 'testing'
TESTROOM1  = 'tester'
TESTUSER0 = 'test@domain.tld'
TESTNICK0 = 'test'
TESTUSER1 = 'tester@domain.tld'
TESTNICK1 = 'tester'
TESTUSER2 = 'testing@domain.tld'
TESTNICK2 = 'testing'

TESTHOST = 'domain.tld'

VALID_ROLES = ['player','participant','moderator','none','visitor']
VALID_AFFILIATIONS = ['player','member','owner','none','admin','outcast']


class DIRStorageTests(unittest.TestCase):
    """
    """

    def setUpClass(self):
        self.storage = dir_storage.Storage('./chat_spool/')
        

    def error(self, err):
        err.raiseException()
        
    def testAcreateRoom(self):
        def ret(room):
            return self.failUnlessIn(TESTROOM0,[room])
    
        d = self.storage.createRoom(TESTROOM0,TESTUSER0) 
        d.addCallback(ret)
        d.addErrback(self.error)
        return d

    def testBcreateRoom(self):
        def ret(room):
            return self.failUnlessIn(TESTROOM1,[room])
    
        d = self.storage.createRoom(TESTROOM1,TESTUSER1) 
        d.addCallback(ret)
        d.addErrback(self.error)
        return d


    def testGetRoom(self):
        def ret(r):
            name = r['name']
            if not r.has_key('locked'):
                self.fail('Bad room')

            if not r.has_key('persistent'):
                self.fail('Bad room')
                
            return self.failUnlessIn(TESTROOM0,[name])
    
        d = self.storage.getRoom(TESTROOM0) 
        d.addCallback(ret)
        d.addErrback(self.error)
        return d

    def testSetSubject(self):
        def ret(r):
            subject = r['subject']
            return self.failUnlessIn('subject test',[subject])
    
        d = self.storage.updateRoom(TESTROOM0, subject ='subject test') 
        d.addCallback(ret)
        d.addErrback(self.error)
        return d


    def testJoinRoom(self):
        def ret(r):
            roster = r['roster']
            user = None
            for r in roster:
                if TESTUSER0 == r['jid']:
                    user = r
                    break
            
            if user['role'] not in VALID_ROLES:
                self.fail('Bad role')
                
            if user['affiliation'] not in VALID_AFFILIATIONS:
                self.fail('Bad role')

            if not user.has_key('status'):
                self.fail('Bad user format')

            if not user.has_key('show'):
                self.fail('Bad user format')

            if not user.has_key('legacy'):
                self.fail('Bad user format')
            return self.failUnless(user)
            
    
        d = self.storage.joinRoom(TESTROOM0, TESTUSER0, TESTNICK0)
        d.addCallback(ret)
        d.addErrback(self.error)
        return d

    def testSetRole(self):
        def ret(r):
            roster = r[TESTROOM0]['roster']
            role = None
            for r in roster:
                if TESTUSER0 == r['jid']:
                    role = r['role']
                    break
                
            return self.failUnlessEqual('participant',role)
    
        d = self.storage.setRole(TESTROOM0, TESTUSER0, 'participant') 
        d.addCallback(ret)
        d.addErrback(self.error)
        return d

    def testSgetRole(self):
        def ret(role):
            return self.failUnlessEqual('participant',role)
    
        d = self.storage.getRole(TESTROOM0, TESTUSER0) 
        d.addCallback(ret)
        d.addErrback(self.error)
        return d

    def testSetXAffiliation(self):
        def ret(r):
            roster = r[TESTROOM0]['roster']
            a = None

            for r in roster:
                if TESTUSER0 == r['jid']:
                    a = r['affiliation']
                    break
                    
            return self.failUnlessEqual('admin',a)
    
        d = self.storage.setAffiliation(TESTROOM0, TESTUSER0, 'admin') 
        d.addCallback(ret)
        d.addErrback(self.error)
        return d

    def testKGetAffiliation(self):
        def ret(r):
            return self.failUnlessEqual('owner',r)
    
        d = self.storage.getAffiliation(TESTROOM0, TESTUSER0) 
        d.addCallback(ret)
        d.addErrback(self.error)
        return d


    def testSetOwner(self):
        def ret(r):
            roster = r['owner']
            user = None
            for r in roster:
                if TESTUSER0 == r:
                    user = r
                    break
            return self.failUnless((user==TESTUSER0))
    
        d = self.storage.setOwner(TESTROOM0, TESTUSER0)
        d.addCallback(ret)
        d.addErrback(self.error)
        return d

    def testSetPlayer(self):
        def ret(r):
            roster = r['player']
            user = None
            for r in roster:
                if TESTUSER0 == r:
                    user = r
                    break
            return self.failUnless((user==TESTUSER0))
    
        d = self.storage.setPlayer(TESTROOM0, TESTUSER0)
        d.addCallback(ret)
        d.addErrback(self.error)
        return d

    def testSetMember(self):
        def ret(r):
            roster = r['member']
            user = None
            for r in roster:
                if TESTUSER1 == r:
                    user = r
                    break
                
            return self.failUnless(user)
            
    
        d = self.storage.setMember(TESTROOM0, TESTUSER1)
        d.addCallback(ret)
        d.addErrback(self.error)
        return d

    def testSetAdmin(self):
        def ret(r):
            roster = r['admin']
            user = None
            for r in roster:
                if TESTUSER0 == r:
                    user = r
                    break
                
            return self.failUnless((user==TESTUSER0))
    
        d = self.storage.setAdmin(TESTROOM0, TESTUSER0)
        d.addCallback(ret)
        d.addErrback(self.error)
        return d

    def testWChangeStatus(self):
        def ret(room):
            roster = room['roster']
            user = {}
            for r in roster:
                if TESTUSER0 == r['jid']:
                    user = r
                    break
                
            return self.failUnless((user['show']=='xa'))
    
        d = self.storage.changeStatus(TESTROOM0, TESTUSER0, show='xa', status="I'm ready")
        d.addCallback(ret)
        d.addErrback(self.error)
        return d

    def testWChangeNick(self):
        def ret(r):
            roster = r['roster']
            user = {}
            for r in roster:
                if TESTUSER0 == r['jid']:
                    user = r
                    break
            if user['role'] not in VALID_ROLES:
                self.fail('Bad role')
                
            if user['affiliation'] not in VALID_AFFILIATIONS:
                self.fail('Bad role')

            if not user.has_key('status'):
                self.fail('Bad user format')

            if not user.has_key('show'):
                self.fail('Bad user format')

            if not user.has_key('legacy'):
                self.fail('Bad user format')                
            return self.failUnless((user['nick']==TESTNICK0))
    
        d = self.storage.changeNick(TESTROOM0, TESTUSER0, TESTNICK0)
        d.addCallback(ret)
        d.addErrback(self.error)
        return d

    def testWGetNicks(self):
        def ret(r):
            return self.failUnlessIn(TESTNICK0, r)
    
        d = self.storage.getNicks(TESTROOM0)
        d.addCallback(ret)
        d.addErrback(self.error)
        return d

    def testXPartRoom(self):
        def ret(rt):
            r = rt[0]
            old_user = rt[1]
            return self.failIfIn(TESTUSER0,r['roster'])
    
        d = self.storage.partRoom(TESTROOM0, TESTUSER0, TESTNICK0) 
        d.addCallback(ret)
        d.addErrback(self.error)
        return d


    def testYZdeleteRoom(self):
        def ret(d):
            return d
    
        d = self.storage.deleteRoom(TESTROOM0,TESTUSER0) 
        d.addCallback(ret)
        d.addErrback(self.error)
        return d

    def testZZdeleteRoom(self):
        def ret(d):
            return d
    
        d = self.storage.deleteRoom(TESTROOM1,TESTUSER1) 
        d.addCallback(ret)
        d.addErrback(self.error)
        return d


class MEMStorageTests(unittest.TestCase):
    """
    """

    def setUpClass(self):
        self.storage = memory_storage.Storage('')
        

    def error(self, err):
        err.raiseException()
        
    def testAcreateRoom(self):
        def ret(room):
            return self.failUnlessIn(TESTROOM0,[room])
    
        d = self.storage.createRoom(TESTROOM0,TESTUSER0) 
        d.addCallback(ret)
        d.addErrback(self.error)
        return d

    def testBcreateRoom(self):
        def ret(room):
            return self.failUnlessIn(TESTROOM1,[room])
    
        d = self.storage.createRoom(TESTROOM1,TESTUSER1) 
        d.addCallback(ret)
        d.addErrback(self.error)
        return d


    def testGetRoom(self):
        def ret(r):
            name = r['name']
            if not r.has_key('locked'):
                self.fail('Bad room')

            if not r.has_key('persistent'):
                self.fail('Bad room')
            return self.failUnlessIn(TESTROOM0,[name])
    
        d = self.storage.getRoom(TESTROOM0) 
        d.addCallback(ret)
        d.addErrback(self.error)
        return d

    def testSetSubject(self):
        def ret(r):
            subject = r['subject']
            return self.failUnlessIn('subject test',[subject])
    
        d = self.storage.updateRoom(TESTROOM0, subject ='subject test') 
        d.addCallback(ret)
        d.addErrback(self.error)
        return d


    def testJoinRoom(self):
        def ret(r):
            roster = r['roster']
            user = None
            for r in roster:
                if TESTUSER0 == r['jid']:
                    user = r
                    break
            if user['role'] not in VALID_ROLES:
                self.fail('Bad role')
                
            if user['affiliation'] not in VALID_AFFILIATIONS:
                self.fail('Bad role')

            if not user.has_key('status'):
                self.fail('Bad user format')

            if not user.has_key('show'):
                self.fail('Bad user format')

            if not user.has_key('legacy'):
                self.fail('Bad user format')
                
            return self.failUnless(user)
            
    
        d = self.storage.joinRoom(TESTROOM0, TESTUSER0, TESTNICK0)
        d.addCallback(ret)
        d.addErrback(self.error)
        return d

    def testSetRole(self):
        def ret(r):
            roster = r[TESTROOM0]['roster']
            role = None
            for r in roster:
                if TESTUSER0 == r['jid']:
                    role = r['role']
                    break
                
            return self.failUnlessEqual('participant',role)
    
        d = self.storage.setRole(TESTROOM0, TESTUSER0, 'participant') 
        d.addCallback(ret)
        d.addErrback(self.error)
        return d

    def testSgetRole(self):
        def ret(role):
            return self.failUnlessEqual('participant',role)
    
        d = self.storage.getRole(TESTROOM0, TESTUSER0) 
        d.addCallback(ret)
        d.addErrback(self.error)
        return d

    def testSetXAffiliation(self):
        def ret(r):
            roster = r[TESTROOM0]['roster']
            a = None

            for r in roster:
                if TESTUSER0 == r['jid']:
                    a = r['affiliation']
                    break
                    
            return self.failUnlessEqual('admin',a)
    
        d = self.storage.setAffiliation(TESTROOM0, TESTUSER0, 'admin') 
        d.addCallback(ret)
        d.addErrback(self.error)
        return d

    def testKGetAffiliation(self):
        def ret(r):
            return self.failUnlessEqual('owner',r)
    
        d = self.storage.getAffiliation(TESTROOM0, TESTUSER0) 
        d.addCallback(ret)
        d.addErrback(self.error)
        return d


    def testSetOwner(self):
        def ret(r):
            roster = r['owner']
            user = None
            for r in roster:
                if TESTUSER0 == r:
                    user = r
                    break
            return self.failUnless((user==TESTUSER0))
    
        d = self.storage.setOwner(TESTROOM0, TESTUSER0)
        d.addCallback(ret)
        d.addErrback(self.error)
        return d

    def testSetPlayer(self):
        def ret(r):
            roster = r['player']
            user = None
            for r in roster:
                if TESTUSER0 == r:
                    user = r
                    break
            return self.failUnless((user==TESTUSER0))
    
        d = self.storage.setPlayer(TESTROOM0, TESTUSER0)
        d.addCallback(ret)
        d.addErrback(self.error)
        return d

    def testSetMember(self):
        def ret(r):
            roster = r['member']
            user = None
            for r in roster:
                if TESTUSER1 == r:
                    user = r
                    break
                
            return self.failUnless(user)
            
    
        d = self.storage.setMember(TESTROOM0, TESTUSER1)
        d.addCallback(ret)
        d.addErrback(self.error)
        return d

    def testSetAdmin(self):
        def ret(r):
            roster = r['admin']
            user = None
            for r in roster:
                if TESTUSER0 == r:
                    user = r
                    break
                
            return self.failUnless((user==TESTUSER0))
    
        d = self.storage.setAdmin(TESTROOM0, TESTUSER0)
        d.addCallback(ret)
        d.addErrback(self.error)
        return d

    def testWChangeStatus(self):
        def ret(roster):
            for r in roster:                
                if TESTUSER0 == r['jid']:
                    user = r
                    break
                
            return self.failUnless((user['show']=='xa'))
    
        d = self.storage.changeStatus(TESTROOM0, TESTUSER0, show='xa', status="I'm ready")
        d.addCallback(ret)
        d.addErrback(self.error)
        return d

    def testWChangeNick(self):
        def ret(r):
            roster = r['roster']
            user = {}
            for r in roster:
                if TESTUSER0 == r['jid']:
                    user = r
                    break
            return self.failUnless((user['nick']==TESTNICK0))
    
        d = self.storage.changeNick(TESTROOM0, TESTUSER0, TESTNICK0)
        d.addCallback(ret)
        d.addErrback(self.error)
        return d

    def testWGetNicks(self):
        def ret(r):
            return self.failUnlessIn(TESTNICK0, r)
    
        d = self.storage.getNicks(TESTROOM0)
        d.addCallback(ret)
        d.addErrback(self.error)
        return d

    def testXPartRoom(self):
        def ret(rt):
            r = rt[0]
            old_user = rt[1]
            return self.failIfIn(TESTUSER0,r['roster'])
    
        d = self.storage.partRoom(TESTROOM0, TESTUSER0, TESTNICK0) 
        d.addCallback(ret)
        d.addErrback(self.error)
        return d


    def testYZdeleteRoom(self):
        def ret(d):
            return d
    
        d = self.storage.deleteRoom(TESTROOM0,TESTUSER0) 
        d.addCallback(ret)
        d.addErrback(self.error)
        return d

    def testZZdeleteRoom(self):
        def ret(d):
            return d
    
        d = self.storage.deleteRoom(TESTROOM1,TESTUSER1) 
        d.addCallback(ret)
        d.addErrback(self.error)
        return d


