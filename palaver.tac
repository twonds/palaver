from twisted.words.protocols.jabber import jid, client
from twisted.application import internet, service
from twisted.internet import interfaces, defer
from twisted.python import usage, log, reflect
from twisted.words.xish import domish, xpath

try:
    from twisted.words.protocols.jabber.component import IService
except:
    from twisted.words.protocols.jabber.ijabber import IService
from twisted.words.protocols.jabber import component

from zope.interface import Interface, implements


from palaver import pgsql_storage
from palaver import palaver
from palaver import muc

application = service.Application("palaver-chat")

# set up Jabber Component
sm = component.buildServiceManager('chat.localhost', 'secret',
                    ("tcp:127.0.0.1:5347" ))

# Turn on verbose mode
palaver.LogService().setServiceParent(sm)

st = pgsql_storage.Storage(user='muc',
                           database='muc',
                           hostname=None,
                           password=None,
                           port=None,
                           apitype='psycopg2'
                           )

sadmins = ['admin@localhost'
          ]
bs = muc.groupchat.GroupchatService(st)

bs.sadmins = sadmins

c = IService(bs)
c.setServiceParent(sm)


bsc = muc.groupchat.RoomService()
bsc.sadmins = sadmins
bsc.create_rooms = 1

bsc.setServiceParent(bs)
IService(bsc).setServiceParent(sm)


bsc = muc.groupchat.AdminService()
bsc.setServiceParent(bs)
bsc.sadmins = sadmins


IService(bsc).setServiceParent(sm)

s = palaver.PalaverService()
s.setServiceParent(sm)

sm.setServiceParent(application)

