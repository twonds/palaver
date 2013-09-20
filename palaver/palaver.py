# -*- coding: utf-8 -*-
# Copyright (c) 2005-2013 Christopher Zorn
# See LICENSE.txt for details
"""
Main service class for multi-user chat.

"""
import time
from twisted.words.protocols.jabber import jid
from twisted.words.protocols.jabber.xmlstream import IQ as xsIQ

from twisted.internet import defer
from twisted.python import log, reflect
from twisted.words.xish import domish

try:
    from twisted.words.protocols.jabber.component import IService
except:
    from twisted.words.protocols.jabber.ijabber import IService
from twisted.words.protocols.jabber import component


from xmpp import jid_unescape

__version__ = '0.6'

from xmpp.ns import *
from xmpp import disco
from xmpp import error


class PalaverService(component.Service):

    def componentConnected(self, xmlstream):
        self.xmlstream = xmlstream
        # TODO - this needs to be done another way
        self.jid = xmlstream.authenticator.otherHost
        xmlstream.addObserver(VERSION, self.onVersion, 1)
        xmlstream.addObserver(DISCO_INFO, self.onDiscoInfo, 1)
        xmlstream.addObserver(DISCO_ITEMS, self.onDiscoItems, 1)
        xmlstream.addObserver(IQ_GET, self.iqFallback, -1)
        xmlstream.addObserver(IQ_SET, self.iqFallback, -1)

    def get_disco_info(self, room = None, host = None, frm=None):
        info = []

        if not room:
            info.append(disco.Feature(DISCO_NS_ITEMS))
            info.append(disco.Feature(NS_VERSION))
            info.append(disco.Feature(NS_MUC))

        return defer.succeed(info)

    def onVersion(self, iq):
        iq.swapAttributeValues("to", "from")
        iq["type"] = "result"
        iq.addElement("name", None, 'Palaver')
        iq.addElement("version", None, __version__)
        self.send(iq)
        iq.handled = True

    def onDiscoInfo(self, iq):
        dl = []
        try:
            room = jid_unescape(jid.internJID(iq['to']).user)
        except:
            room = None
        host = jid.internJID(iq['to']).host
        for c in self.parent:
            if IService.providedBy(c):
                if hasattr(c, "get_disco_info"):
                    dl.append(c.get_disco_info(room=room, host=host, frm=iq['from']))
        iq.handled = True
        d = defer.DeferredList(dl, fireOnOneErrback=1, consumeErrors=1)
        d.addCallback(self._disco_info_results, iq, room)
        d.addErrback(self._error, iq)
        d.addCallback(self.send)

    def _disco_info_results(self, results, iq, room = None):
        info = []
        for i in results:
            info.extend(i[1])

        # a better fix to the twisted bug is just create a new iq 
        riq = xsIQ(self.xmlstream, 'result')

        riq['id']   = iq['id']
        riq['to']   = iq['from']
        riq['from'] = iq['to']
        riq.addElement('query', DISCO_NS_INFO)

        if room and not info:
            return error.error_from_iq(iq, 'item-not-found')
        else:
            for item in info:
                item.parent = riq.query

                riq.query.addChild(item)

        iq.handled = True
        return riq

    def _error(self, result, iq):
        args = getattr(result.value, 'args', None)
        if not args:
            result.value[0].printBriefTraceback()
        return error.error_from_iq(iq, 'internal-server-error')

    def onDiscoItems(self, iq):
        dl = []
        node = iq.query.getAttribute("node")
        try:
            room = jid_unescape(jid.internJID(iq['to']).user)
        except:
            room = None

        host = jid.internJID(iq['to']).host
        nick = jid.internJID(iq['to']).resource

        for c in self.parent:
            if IService.providedBy(c):
                if hasattr(c, "get_disco_items"):
                    dl.append(c.get_disco_items(room=room, host=host, frm=iq['from'], nick=nick, node=node))
        iq.handled = True
        d = defer.DeferredList(dl, fireOnOneErrback=1, consumeErrors=1)
        d.addCallback(self._disco_items_result, iq, room)
        d.addErrback(self._error, iq)
        d.addCallback(self.send)


    def _disco_items_result(self, results, iq, room = None, node = None):
        # a better fix to the twisted bug is just create a new iq
        riq = xsIQ(self.xmlstream, "result")
        riq['id']   = iq['id']
        riq['to']   = iq['from']
        riq['from'] = iq['to']
        riq.addElement('query', DISCO_NS_ITEMS)
        if node:
            riq.query['node'] = node
        items = []
        for i in results:
            if len(i[1])>0:
                if i[1][0].name == 'error':
                    riq['type'] = 'error'
                    riq.addChild(i[1][0])
                    continue
            items.extend(i[1])

        riq.query.children = items

        iq.handled = True
        return riq

    def iqFallback(self, iq):
        if iq.handled == True:
            return
        self.send(error.error_from_iq(iq, 'service-unavailable'))

class LogService(component.Service):

    def transportConnected(self, xmlstream):
        xmlstream.rawDataInFn = self.rawDataIn
        xmlstream.rawDataOutFn = self.rawDataOut

    def rawDataIn(self, buf):
        log.msg("%s - RECV: %s" % (str(time.time()), unicode(buf, 'utf-8').encode('ascii', 'replace')))

    def rawDataOut(self, buf):
        log.msg("%s - SEND: %s" % (str(time.time()), unicode(buf, 'utf-8').encode('ascii', 'replace')))

class ConfigParser:
    """
    A simple stream parser for configuration files.
    """
    def __init__(self):
        # Setup the parser
        self.stream = domish.elementStream()
        self.stream.DocumentStartEvent = self.onDocumentStart
        self.stream.ElementEvent = self.onElement
        self.stream.DocumentEndEvent = self.onDocumentEnd
        self.config = None

    def parse(self, file):
        f   = open(file)
        buf = f.read()
        f.close()
        self.stream.parse(buf)
        return self.config

    def serialize(self, obj):
        if isinstance(obj, domish.Element):
            obj = obj.toXml()
        return obj

    def onDocumentStart(self, rootelem):
        self.config = rootelem


    def onElement(self, element):
        self.config.addChild(element)


    def onDocumentEnd(self):
        pass


    def _reset(self):
        # Setup the parser
        self.stream = domish.elementStream()
        self.stream.DocumentStartEvent = self.onDocumentStart
        self.stream.ElementEvent = self.onElement
        self.stream.DocumentEndEvent = self.onDocumentEnd


def makeService(config):
    serviceCollection = service.MultiService()
    cf = None
    try:
        p  = ConfigParser()
        cf = p.parse(config['config'])
    except:
        pass
    
    if not config['jid'] and cf:
        jname = str(getattr(cf,'name','palaver'))
        #jname = 'palaver'
        for e in cf.elements():
            if e.name == 'name':
                jname = str(e)
        
    elif config['jid']:
        jname = config['jid']
    else:
        jname = 'palaver'

    
    if not config['secret'] and cf:
        jsecret = str(getattr(cf, 'secret', 'secret'))
    else:
        jsecret = config['secret']
        
    if not config['rhost']  and cf:
        rhost = str(getattr(cf, 'ip', 'localhost'))
    else:
        rhost = config['rhost']

    if not config['rport']  and cf:
        rp    = getattr(cf, 'port', 5347)
        if rp:
            rport = int(str(rp))
        else:
            rport = 5347
    else:
        rport = int(config['rport'])

    if not config['spool']  and cf:
        spool = str(getattr(cf, 'spool', ''))
    else:
        spool = config['spool']
    
    # set up Jabber Component
    sm = component.buildServiceManager(jname, jsecret,
            ("tcp:%s:%s" % (rhost , rport)))

    if config["verbose"]:
        LogService().setServiceParent(sm)

    if cf:
        backend = getattr(cf.backend,'type',None)
        if backend:
            config['backend'] = str(backend)
            if config['backend'] != 'memory' and \
               config['backend'] != 'dir':
                dbuser = getattr(cf.backend,'dbuser',None)
                if dbuser:
                    config['dbuser'] = str(dbuser)
                dbname = getattr(cf.backend,'dbname',None)
                if dbname:
                    config['dbname'] = str(dbname)
                dbpass = getattr(cf.backend,'dbpass',None)
                if dbpass:
                    config['dbpass'] = str(dbpass)
                else:
                    config['dbpass'] = None

                dbport = getattr(cf.backend,'dbport',None)
                if dbport:
                    config['dbport'] = str(dbport)
                else:
                    config['dbport'] = None                    
                    
                dbhostname = getattr(cf.backend,'dbhostname',None)
                if dbhostname:
                    config['dbhostname'] = str(dbhostname)
                else:
                    config['dbhostname'] = None
    config['plugins'] = {}
    if cf:
        if getattr(cf,'plugins',None):
            for p in cf.plugins.elements():
                plugin = reflect.namedModule(str(p))
                config['plugins'][str(p.name)] = plugin.Plugin()
                
                
    if config['backend'] == 'dir':
        import dir_storage
        st = dir_storage.Storage(spool)
    elif config['backend'] == 'memory':
        import memory_storage
        st = memory_storage.Storage()
    elif config['backend'] == 'pgsql':
        import pgsql_storage
        if config['dbhostname']:
            host = config['dbhostname']
        else:
            host = None

        if config['dbpass']:
            dbpass = config['dbpass']
        else:
            dbpass = None
            
        if config['dbport']:
            dbport = config['dbport']
        else:
            dbport = None
            
            
        st = pgsql_storage.Storage(user=config['dbuser'],
                                   database=config['dbname'],
                                   hostname=host,
                                   password=dbpass,
                                   port=dbport,
                                   )
        
    elif config['backend'] == 'psycopg':
        import psycopg_storage
        if config['dbhostname']:
            host = config['dbhostname']
        else:
            host = None

        if config['dbpass']:
            dbpass = config['dbpass']
        else:
            dbpass = None
            
        st = psycopg_storage.Storage(user=config['dbuser'],
                                   database=config['dbname'],
                                   hostname=host,
                                   password=dbpass,
                                   )        
        
    sadmins = []
    conference = getattr(cf,'conference', None)
    if conference:
        sa = getattr(conference, 'sadmin', None)
        if sa:
            for u in sa.elements():
                sadmins.append(str(u))

    if len(sadmins)>0:
        st.sadmins = sadmins

    import groupchat as g
    bs = g.GroupchatService(st)
    if len(sadmins)>0:
        bs.sadmins = sadmins
    bs.plugins = config['plugins']
    
    c = IService(bs)
    c.setServiceParent(sm)

    bsc = g.RoomService()
    bsc.plugins = config['plugins']
    bsc.create_rooms = config['create']
    if len(sadmins)>0:
        bsc.sadmins = sadmins
        
        
    bsc.setServiceParent(bs)
    rs = IService(bsc)
    if len(config['log'])>1:
        import plog
        rs.logger = plog.HTMLLogger(config['log'])
        
    rs.setServiceParent(sm)

    if config['admin']==1:
        bsc = g.AdminService()
        bsc.plugins = config['plugins']
        bsc.setServiceParent(bs)
        if len(sadmins)>0:
            bsc.sadmins = sadmins
        
        IService(bsc).setServiceParent(sm)
        

    s = PalaverService()
    s.setServiceParent(sm)
    
    sm.setServiceParent(serviceCollection)


    return serviceCollection
