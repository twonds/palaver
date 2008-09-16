# Copyright (c) 2005-2007 Christopher Zorn, OGG, LLC
# See LICENSE.txt for details
#
# auth, cred and administration classes for administrating palaver and
# rooms in palaver.
#

from twisted.cred import portal, checkers, credentials, error as credError

from twisted.words.protocol.jabber import jid,client

from zope.interface import Interface, implements

import cred

# Web based administration of palaver


