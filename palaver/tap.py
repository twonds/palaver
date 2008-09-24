# Copyright (c) 2005 - 2007 Christopher Zorn, OGG, LLC 
# See LICENSE.txt for details
from twisted.words.protocols.jabber import component
from twisted.application import internet, service
from twisted.internet import interfaces
from twisted.python import usage
from twisted.words.xish import domish, xpath


import palaver

class Options(usage.Options):
        optParameters = [
                ('rhost', None, None),
                ('rport', None, None),
		('jid', None, None),
                ('secret',None, None),
		('backend',None,'dir'),
		('spool',None, None),
		('admin', None, 1),
		('create', None, 1),
		('dbname',None, 'muc'),
		('dbuser',None, 'muc'),
		('dbhostname',None, None),
		('log', 'l', './html/logs/'),
                ('config', 'c', 'config.xml'),
        ]

        optFlags = [
                ('verbose', 'v', 'Show traffic'),
        ]

def makeService(config):
        return palaver.makeService(config)
