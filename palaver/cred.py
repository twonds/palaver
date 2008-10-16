# Copyright (c) 2005-2008 Christopher Zorn, OGG, LLC 
# See LICENSE.txt for details
"""
XMPP credential classes
"""

from twisted.cred import portal, checkers, credentials, error as credError
from twisted.internet import protocol, reactor, defer
from zope.interface import Interface, implements
from twisted.python import log, failure
from twisted.words.protocols.jabber import client, xmlstream, jid
from twisted.protocols import basic

class XMPPChecker(object):
    implements(checkers.ICredentialsChecker)
    # TODO - other interfaces?
    credentialInterfaces = (credentials.IUsernamePassword,)
    def __init__(self,server=None, port=5222,v=0):
        self.server   = server
        self.port     = int(port)
        self.v        = v
        
        
    def _cbPasswordMatch(self, xs):
        if xs:
            # TODO - send xmlstream 
            xs.send('</stream:stream>')
            xs = None
            return self.myJid
        else:
            return failure.Failure(credError.UnauthorizedLogin())

    def requestAvatarId(self, credentials):
        if credentials.username == "":
            return failure.Failure(credError.UnauthorizedLogin())
        if credentials.password == "":
            return failure.Failure(credError.UnauthorizedLogin())
        
        return defer.maybeDeferred(
            self.login,
            credentials.username,
            credentials.password).addCallback(
            self._cbPasswordMatch)


    def login(self, username, password):
        self.d = defer.Deferred()
        self.myJid = jid.JID(username)
        if self.myJid.resource is None:
            self.myJid.resource = 'XMPPCred'
            
        self.jfactory = client.basicClientFactory(self.myJid, password)
        # TODO - clean this up
        self.jfactory.addBootstrap("//event/stream/authd",self.authd)
        self.jfactory.addBootstrap("//event/client/basicauth/invaliduser", self.authe)
        self.jfactory.addBootstrap("//event/client/basicauth/authfailed", self.authe)
        self.jfactory.addBootstrap("//event/stream/error", self.authe)
        reactor.connectTCP(self.server,self.port,self.jfactory)
        return self.d
    
    def authd(self, xmlstream):
        if not self.d.called:
            self.d.callback(xmlstream)

    def authe(self, e):
        if not self.d.called:
            self.d.errback(e)
        if self.jfactory:
            self.jfactory.stopTrying()
            self.jfactory = None

class IXMPPAvatar(Interface):
    "should have attributes jid, username, host and resource"


class XMPPAvatar:
    implements(IXMPPAvatar)

    def __init__(self, user):
        self.jid      = user
        self.username = self.jid.user
        self.host     = self.jid.host
        self.resource = self.jid.resource
        

class XMPPRealm:
    implements(portal.IRealm)

    def requestAvatar(self, avatarId, mind, *interfaces):
        if IXMPPAvatar in interfaces:
            # TODO - pass along xmlstream?
            #        use self.logout when we do
            logout = lambda: None
            return (XMPPAvatar(avatarId),
                    IXMPPAvatar,
                    logout)
        else:
            raise KeyError("None of the requested interfaces is supported") 
            

    def logout(self):
        self.xs.send('</stream:stream>')
        self.xs = None

# These tests are examples taken from the twisted book
# http://www.oreilly.com/catalog/twistedadn/
class LoginTestProtocol(basic.LineReceiver):
    def lineReceived(self, line):
        cmd = getattr(self, 'handle_' + self.currentCommand)
        cmd(line.strip())

    def connectionMade(self):
        self.transport.write("User Name: ")
        self.currentCommand = 'user'

    def handle_user(self, username):
        self.username = username
        self.transport.write("Password: ")
        self.currentCommand = 'pass'

    def handle_pass(self, password):
        creds = credentials.UsernamePassword(self.username, password)
        self.factory.portal.login(creds, None, IXMPPAvatar).addCallback(
            self._loginSucceeded).addErrback(
            self._loginFailed)

    def _loginSucceeded(self, avatarInfo):
        avatar, avatarInterface, logout = avatarInfo
        self.transport.write("Welcome %s!\r\n" % avatar.jid.full().encode('utf-8'))
        defer.maybeDeferred(logout).addBoth(self._logoutFinished)

    def _logoutFinished(self, result):
        self.transport.loseConnection()

    def _loginFailed(self, failure):
        self.transport.write("Denied: %s.\r\n" % failure.getErrorMessage())
        self.transport.loseConnection()
    
class LoginTestFactory(protocol.ServerFactory):
    protocol = LoginTestProtocol

    def __init__(self, portal):
        self.portal = portal

if __name__ == "__main__":
    p = portal.Portal(XMPPRealm())
    p.registerChecker(XMPPChecker('thetofu.com',5222))
    factory = LoginTestFactory(p)
    reactor.listenTCP(2323, factory)
    reactor.run()
