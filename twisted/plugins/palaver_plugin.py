# Copyright (c) 2005 - 2013 Christopher Zorn
# See LICENSE.txt for details
from zope.interface import implements

from twisted.python import usage
from twisted.plugin import IPlugin
from twisted.application.service import IServiceMaker


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

#def makeService(config):
#        return palaver.makeService(config)

class ServiceFactory(object):
    implements(IServiceMaker, IPlugin)
    tapname = "palaver"
    description = "An XMPP Multi-User Chat component"
    options = Options

    def makeService(self, options):
        return palaver.makeService(options)

service = ServiceFactory()
