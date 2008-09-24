"""
Log palaver rooms
"""
import os, sys
from twisted.words.protocols.jabber import jid, component
from twisted.internet import  defer
from twisted.words.xish import domish, xpath

import datetime, time

from twisted.enterprise import adbapi
from twisted.python import log, threadable, logfile

# TODO - replace this with a template
CSS = """
<style >
body {
    font-family: 'Lucida Grande', Tahoma, Sans-Serif;
    font-size: 12px;
}

h4 {
    font-size: 12px;
    margin: 0 0 7px 0;
}

a img {
    border: none;
}



#header {
    margin: 0;
    padding: 0;
    height: 46px;

    clear: both;
}

table,td,tr,th {
    border: 0px solid;
    border-collapse: collapse;
}

#content {
 clear: both;
    width: 760px;
    background-color: #E8E6E7;
    padding: 15px 10px;
}

#room {
    padding: 15px 10px;
}



#nav {
    float: right;
    margin: 8px 0 0 0;
    padding: 0;
}

#nav li {
    display: inline;
    padding: 0 11px 0 8px;
    border-right: 1px solid #DEB543;
}

#nav li#nav-room {
    border-right: none;
}

#nav-home, #nav-room {
    font-weight: bold;
}

#nav li a {
    text-decoration: none;
}

#nav li a:link {
    color: #716F70;
}

#nav li a:visited {
    color: #716F70;
}

#nav li a:hover {
    color: #91450A;
}

#nav li a:active {
}



#wrap {
    width: 780px;
    padding: 10px;
    margin: 0 auto;
}

.emit {
 width: 100%%;
 color: #91450A;
 border-bottom: 1px solid #DEB543;
}

.message {
 width: 100%%;
 color: black;
}

.emit a {
    width: 100%%;
}

.raw {
    color: black;
    font-size: 8px;
    display:none;
}

    </style>
    """

HTML_HEAD = """
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
  <head>
    <meta content="text/html; charset=utf-8" http-equiv="content-type" />
    %s 
    <title>Palaver - %s</title>
      </head>
  <body id="room">
   <div id="wrap">
      <ul id="nav">

        <li id="nav-home"><a href="">Home</a></li>
        <li id="nav-room"><a href="%s/%s.html">Room</a></li>
      </ul>
      <div id="header">
        <h1>Room : %s</h1>
      </div>


      <div id="content">
      """


HTML_FOOT = """</div></div></body></html>"""


class DailyLogger(logfile.DailyLogFile):

    header = HTML_HEAD
    footer = HTML_FOOT
    css    = CSS
    cssurl = None
    
    def __init__(self, name, directory, defaultMode=None):
        self.title = name
        new_directory = self._getNewDirectory(directory, name)
        name = name +'.html'
        logfile.DailyLogFile.__init__(self, name, new_directory, defaultMode=defaultMode)
        self.directory = new_directory

    def _getNewDirectory(self, directory, name):
        if not os.path.isdir(directory +'/'):
            os.mkdir(directory +'/')                    
        if not os.path.isdir(directory +'/'+ name):
            os.mkdir(directory +'/'+ name)                    
        new_directory = directory +'/'+ name
        return new_directory

    def _openFile(self):
        logfile.DailyLogFile._openFile(self)
        # add header
        self.size = self._file.tell()
        if self.size <= 0:
            if self.cssurl:
                css = self.cssurl
            else:
                css = self.css
                
            self.write(self.header % (css, self.title, self.title , self.directory, self.title))

    def write(self, data):
        """
        Write some data to the file.
        """

        # remove and write footer
        if self.size > 0:
            self._file.seek(self.size-len(self.footer))
        
        logfile.DailyLogFile.write(self, data+self.footer)
        self.size = self._file.tell()
        


        
threadable.synchronize(DailyLogger)

class LogPublisher(log.LogPublisher):
    pass

class PgSQLLogger:
    """
    A postgresql log data collector for muc.
    """
    TYPES = {'join':0,
             'leave':1,
             'message':3,
             'topic':4,
             'error':5,
             
             }
    
    def __init__(self,
                 user,
                 database,
                 password=None,
                 hostname=None,
                 port=None):
        self._user = user
        self._database = database
        self._password = password
        self._hostname = hostname
        self._port = port
        self._dbpool = None
        
    def _createLogger(self):
        try:
            from twisted.enterprise.adbapi import Psycopg2ConnectionFactory as cf
            conn_string = "dbname=%s" % self._database
            conn_string = "user=%s %s" % (self._user, conn_string)
            if self._password:
                conn_string += " password='%s'" %  self._password
            if self._hostname:
                conn_string += " host=%s" % self._hostname
            else:
                conn_string += " host=''" 
            if self._port:
                conn_string += " port=%s" % self._dbport

            apitype = cf(conn_string)
            self._dbpool = adbapi.ConnectionPool(apitype)
            
        except Exception, ex:
            print str(ex)
        

            
    def joinRoom(self, user, room, host):
        """
        insert a log that the user joined the room
        """
        join_room_query = "INSERT into palaver_log (\"user\", \"room\", \"host\", \"type\") VALUES ('%s', '%s', '%s', %d)"%(str(user),str(room),str(host),PgSQLLogger.TYPES['join']);
        self._dbpool.runQuery(join_room_query,self._user)
        
    def partRoom(self, user, room, reason, host):
        """
        log that the user left the room
        """
        part_room_query = "INSERT into palaver_log (\"user\", \"room\", \"host\", \"type\", \"message\") VALUES ('%s', '%s', '%s', %d, '%s')"%(str(user),str(room),str(host),PgSQLLogger.TYPES['leave'],reason);
        self._dbpool.runQuery(part_room_query,self._user)
        
    def groupchat(self, user, room, body, host):
        """
        Log a message that came to a room
        """
        message_room_query = "INSERT into palaver_log (\"user\", \"room\", \"host\", \"type\", \"message\") VALUES ('%s', '%s', '%s', %d, '%s')"%(str(user),str(room),str(host),PgSQLLogger.TYPES['message'],str(body));
        
        self._dbpool.runQuery(message_room_query,self._user)
        


    def changeTopic(self,user,room,topic,host):
        """
        log when the topic has been changed.
        """
        topic_room_query = "INSERT into palaver_log (\"user\", \"room\", \"host\", \"type\", \"message\") VALUES ('%s', '%s', '%s', %d, '%s')"%(str(user),str(room),str(host),PgSQLLogger.TYPES['topic'],str(topic));
        
        self._dbpool.runQuery(topic_room_query,self._user)

        
    def error(self, user, room, host, message):
        """
        insert an error that has been logged
        """
        error_room_query = "INSERT into palaver_log (\"user\", \"room\", \"host\", \"type\", \"message\") VALUES ('%s', '%s', '%s', %d, '%s')"%(str(user),str(room),str(host),PgSQLLogger.TYPES['error'],str(message));
        
        self._dbpool.runQuery(error_room_query,self._user)


    def log(self, room, host, nick, elements):
        """
        log room data based on given elements
        """
        if not self._dbpool:
            self._createLogger()
            
        for e in elements:
            div_class = 'raw'
            if e.name == 'presence' and e.hasAttribute('type'):

                msg = str(nick) + ' has left the room'
                self.partRoom(str(nick),room,msg,host)
                
            elif e.name == 'presence' and not e.hasAttribute('type') and not getattr(e, 'status', None) and not getattr(e, 'show', None):
                
                self.joinRoom(nick, room, host)
                    
            elif e.name == 'message' and getattr(e, 'subject', None):
                                
                self.changeTopic(str(nick),room,str(e.subject),host)
                
            elif e.name == 'message' and e.hasAttribute('type') and e['type'] == 'groupchat' and getattr(e, 'body', None):
                msg = ""
                try:
                    msg  =  unicode(nick) + u' : ' + e.body.__str__()
                except:
                    msg = nick + ':' + '????? Unicode error'
                self.groupchat(str(nick),room,msg,host)
            else:
                msg = domish.escapeToXml(e.toXml())
                self.error(nick,room,host,msg)
                
        
class HTMLLogObserver(log.FileLogObserver):

    def emit(self, eventDict):
        try:
            timeStr = self.formatTime(eventDict['time'])
        except:
            timeStr = ""

        msgStr = "".join(eventDict['message'])

        log.util.untilConcludes(self.write, "<div class='emit'>[" + timeStr + "] " + msgStr + "</div>")
        log.util.untilConcludes(self.flush)  

class PalaverLogService(component.Service):

    def transportConnected(self, xmlstream):
        xmlstream.addObserver("/presence", self.onElement, 10)
        xmlstream.addObserver("/message[@type='groupchat']", self.onElement, 10)

    def onElement(self, elem):
        pass 


class HTMLLogger:

    def __init__(self, log_dir = './logs/html'):
        self.log_dir = log_dir
        self.loggers = {}
        self.nicks   = {} # in memory nicks, delete when changed or leave
    
    def _getOrCreateLog(self, lid):
        if not self.loggers.has_key(lid):
            if not os.path.isdir(self.log_dir +'/'):
                os.mkdir(self.log_dir +'/')                    
            logPath = os.path.abspath(self.log_dir+'/'+lid+'/')
            logFile = DailyLogger(os.path.basename(logPath),
                                  os.path.dirname(logPath))
        
            #self.startLogging
            self.loggers[lid] = self._startLogging(logFile)

        return self.loggers[lid]

    def _startLogging(self, file):
        """Initialize logging to a specified file.
        """
        flo = HTMLLogObserver(file)
        logp = LogPublisher()
        logp.addObserver(flo.emit)
        return logp

    
    def log(self, room, host, nick, elements):
        
        # create or grab loggers for each to and from
        logger  = self._getOrCreateLog(host+'/'+room)
                
        for e in elements:
            div_class = 'raw'
            if e.name == 'presence' and e.hasAttribute('type'):
                div_class = 'leave'
                msg = str(nick) + ' has left the room'
            elif e.name == 'presence' and not e.hasAttribute('type') and not getattr(e, 'status', None) and not getattr(e, 'show', None):
                div_class = 'join'
                msg = str(nick) + ' has joined the room'    
            elif e.name == 'message' and getattr(e, 'subject', None):
                div_class = 'new_subject'
                msg = str(nick) + ' has changed the topic to ' + str(e.subject)
            elif e.name == 'message' and e.hasAttribute('type') and e['type'] == 'groupchat' and getattr(e, 'body', None):
                div_class = 'message'
                try:
                    msg  =  unicode(nick) + u' : ' + e.body.__str__()
                except:
                    msg = nick + ':' + '????? Unicode error'
            else:
                msg = domish.escapeToXml(e.toXml())
                
            logger.msg("<span class='%s'><a name='%s'> %s </a></span>" % (div_class, str(time.time()), msg.encode('ascii', 'replace'), ))
            
        
    

class HTMLLogService(PalaverLogService, HTMLLogger):
    """
    HTML Room Logger
    """
    log_dir = './logs/html/'
    loggers = {}
    nicks   = {} # in memory nicks, delete when changed or leave
    
    
    def onElement(self, elem):
        
        # get room, nick and host
        room, hostnick = elem['to'].split("@")

        hlist = hostnick.split("/")
        nick = None
        host = hlist[0]
        if len(hlist)>1:
            nick = hlist[1]
            self.nicks[elem['from'].lower()+room.lower()+host.lower()] = nick
            if elem.name == 'presence' and elem.hasAttribute('type'):
                if self.nicks.has_key(elem['from'].lower()+room.lower()+host.lower()):
                    del self.nicks[elem['from'].lower()+room.lower()+host.lower()] 
        else:
            if self.nicks.has_key(elem['from'].lower()+room.lower()+host.lower()):
                nick = self.nicks[elem['from'].lower()+room.lower()+host.lower()]
        
        self.log(room, host, nick, [elem])

class XMLLogService(PalaverLogService):

    """
    XML Room Logger
    """
    log_dir = './logs/xml/'

    def onElement(self, elem):
        log.msg(elem.toXml())
        # get room, nick and host
        room, hostnick = elem['from'].split("@")
        host, nick = hostnick.split("/")[0]


