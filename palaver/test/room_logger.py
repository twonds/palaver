from twisted.trial import unittest
import palaver.plog
from twisted.words.xish import domish
from palaver.xmpp.ns import *
class RoomLoggerTest(unittest.TestCase):

    def testHtmlLogger(self):
        """ Test the html logger. """
        logger = palaver.plog.HTMLLogger('/tmp/')

        message = domish.Element((NS_CLIENT,'message'))
        message['to']   = "testdude@somedomain.com"
        message['from'] = "testroom@somedomain.com/nick"
        message['type'] = 'normal'
        message.addElement('body',
                           None,
                           'You have been invited to testroom@somedomain.com/nick') 
        message.addElement('subject', None, 'Invite')
        logger.log('testroom',
                   'chat.somedomain.com',
                   'testdude@somedomain.com',
                   [message])

        
    def testPgSQLLogger(self):
        """ Test the postgresql logger. """

        logger = palaver.plog.PgSQLLogger("chesspark","speeqe")
