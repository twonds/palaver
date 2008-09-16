# Copyright (c) 2005 Christopher Zorn, OGG, LLC 
# See LICENSE.txt for details
from twisted.words.protocols.jabber import jid, client, component
from twisted.application import internet, service
from twisted.internet import interfaces, defer
from twisted.python import usage
from twisted.words.xish import domish, xpath


from zope.interface import Interface, implements



class IStorage(Interface):

    """
    The backend class for multi-user chat
    """

    def createRoom(self, room, user):
        """
        Create a multi-user chat room
        """

    def deleteRoom(self, room, user):
        """
        Delete a multi-user chat room
        """
        
    def setRoomSubject(self, room, subject):
        """
        """

    def getRoomSubject(self, room, subject):
        """
        """


