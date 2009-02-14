"""A stanza queue to prevent race conditions and other things. 
"""
from twisted.internet import task

class StanzaQueue(object):
    """
    """

    def __init__(self, cb_presence = None, cb_groupchat = None):
        self.started = False
        self.stz_pending = {}
                
        self.delayed_queue = []
        self.delayed_queue_call = None

        self.onPresence  = cb_presence
        self.onGroupChat = cb_groupchat
        self.onIqAdmin   = None

    def start(self):
        if not self.started:
            self.delayed_queue_call = task.LoopingCall(self._handleDelayedQueue)
            self.delayed_queue_call.start(1)
            self.started = True
        
    def _handleDelayedQueue(self):
        new_queue = []

        while len(self.delayed_queue) > 0:
            d = self.delayed_queue.pop()

            if self.stz_pending.has_key(d['room'].lower()+d['stz']['from'].lower()):
                # wait patiently 
                new_queue.append(d)
            elif d['stz'].name == 'presence' and self.onPresence:
                self.onPresence(d['stz'])
            elif d['stz'].name == 'message' and self.onGroupChat:
                self.onGroupChat(d['stz'])                
            elif d['stz'].name == 'iq' and self.onIqAdmin:
                self.onIqAdmin(d['stz'])                

        self.delayed_queue = new_queue


    def doDelay(self, room, frm, stz):
        if self.stz_pending.has_key(room.lower()+frm.lower()):
            # add to delayed queue
            self.delayed_queue.append({'room': room, 'stz': stz})
            return True
        self.stz_pending[room.lower()+frm.lower()] = True
        return False

    def _delStzPending(self, room, user):
        if self.stz_pending.has_key(room.lower()+user.lower()):
            del self.stz_pending[room.lower()+user.lower()]


