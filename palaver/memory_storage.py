# Copyright (c) 2005 - 2007 Christopher Zorn, OGG, LLC 
# See LICENSE.txt for details

from twisted.internet import defer, reactor
from twisted.python import log
from twisted.words.protocols.jabber import jid
from zope.interface import implements


def StorageError(Error):
    pass

# maybe move groupchat
import groupchat
import storage
import dir_storage

class Storage(dir_storage.Storage):

    def __init__(self, spool):
        self.spool_dir = spool
        self.rooms = spool + '/rooms.xml'
        self.spool = {}
        if not self.spool.has_key('rooms'):
            self.spool['rooms'] = {}
        
