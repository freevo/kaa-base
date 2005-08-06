# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# event.py - Event handling for the notifier
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# kaa-notifier - Notifier Wrapper
# Copyright (C) 2005 Dirk Meyer, et al.
#
# First Version: Dirk Meyer <dmeyer@tzi.de>
# Maintainer:    Dirk Meyer <dmeyer@tzi.de>
#
# Please see the file doc/AUTHORS for a complete list of authors.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of MER-
# CHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General
# Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA
#
# -----------------------------------------------------------------------------

__all__ = [ 'Event', 'EventHandler', 'WeakEventHandler' ]

# python imports
import copy
import logging

# kaa.notifier imports
from callback import NotifierCallback, WeakNotifierCallback
from thread import MainThreadCallback, is_mainthread
from timer import OneShotTimer

# get logging object
log = logging.getLogger('notifier')

# manager object for eveny handling
manager = None

class Event(object):
    """
    A simple event that can be passed to the registered event handler.
    """
    def __init__(self, name, *args):
        """
        Init the event.
        """
        if isinstance(name, Event):
            self.name = name.name
            self.arg  = name.arg
        else:
            self.name = name
            self.arg  = None
        if args:
            self._set_args(args)

            
    def _set_args(self, args):
        """
        Set arguments of the event.
        """
        if not args:
            self.arg = None
        elif len(args) == 1:
            self.arg = args[0]
        else:
            self.arg = args


    def post(self, *args):
        """
        Post event into the queue.
        """
        event = self
        if args:
            event = copy.copy(self)
            event._set_args(args)
        if not is_mainthread():
            return MainThreadCallback(manager.post, event)()
        else:
            return manager.post(event)

        
    def __str__(self):
        """
        Return the event as string
        """
        return self.name


    def __cmp__(self, other):
        """
        Compare function, return 0 if the objects are identical, 1 otherwise
        """
        if not other:
            return 1
        if isinstance(other, Event):
            return self.name != other.name
        return self.name != other


class EventHandler(NotifierCallback):
    """
    Event handling callback.
    """
    def register(self, events=[]):
        """
        Register to a list of events. If no event is given, all events
        will be used.
        """
        self.events = events
        if not self in manager.handler:
            manager.handler.append(self)


    def active(self):
        """
        Return if the object is bound to the event manager.
        """
        return self in manager.handler

    
    def unregister(self):
        """
        Unregister callback.
        """
        if self in manager.handler:
            manager.handler.remove(self)


    def __call__(self, event):
        """
        Call callback if the event matches.
        """
        if not self.events or event in self.events:
            super(EventHandler, self).__call__(event)


class WeakEventHandler(WeakNotifierCallback, EventHandler):
    """
    Weak reference version of the EventHandler.
    """
    pass


class EventManager(object):
    """
    Class to manage Event and EventHandler objects.
    Internal use only.
    """
    def __init__(self):
        self.queue = []
        self.locked = False
        self.timer = OneShotTimer(self.handle)
        self.handler = []


    def post(self, event):
        """
        Add event to the queue.
        """
        self.queue.append(event)
        if not self.timer.active():
            self.timer.start(0)
        

    def handle(self):
        """
        Handle the next event.
        """
        if self.locked:
            self.timer.start(0.01)
            return
        if not self.queue:
            return
        self.locked = True
        event = self.queue[0]
        self.queue = self.queue[1:]
        
        try:
            for handler in copy.copy(self.handler):
                handler(event)
        except:
            log.exception('event callback')
        self.locked = False
        if self.queue and not self.timer.active():
            self.timer.start(0)

manager = EventManager()
