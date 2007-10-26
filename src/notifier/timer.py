# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# timer.py - Timer classes for the notifier
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# kaa.notifier - Mainloop and callbacks
# Copyright (C) 2005-2007 Dirk Meyer, Jason Tackaberry, et al.
#
# First Version: Dirk Meyer <dmeyer@tzi.de>
# Maintainer:    Dirk Meyer <dmeyer@tzi.de>
#                Jason Tackaberry <tack@urandom.ca>
#
# Please see the file AUTHORS for a complete list of authors.
#
# This library is free software; you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License version
# 2.1 as published by the Free Software Foundation.
#
# This library is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301 USA
#
# -----------------------------------------------------------------------------

__all__ = [ 'Timer', 'WeakTimer', 'OneShotTimer', 'WeakOneShotTimer',
            'AtTimer', 'OneShotAtTimer' ]

import logging
import time

import nf_wrapper as notifier
from thread import MainThreadCallback, is_mainthread

# get logging object
log = logging.getLogger('notifier')

class Timer(notifier.NotifierCallback):

    def __init__(self, callback, *args, **kwargs):
        super(Timer, self).__init__(callback, *args, **kwargs)
        self.restart_when_active = True
        self._interval = None


    def start(self, interval):
        if not is_mainthread():
            return MainThreadCallback(self.start, interval)()

        if self.active():
            if not self.restart_when_active:
                return
            self.unregister()

        self._id = notifier.timer_add(int(interval * 1000), self)
        self._interval = interval


    def stop(self):
        if not is_mainthread():
            return MainThreadCallback(self.stop)()
        self.unregister()


    def unregister(self):
        if self.active():
            notifier.timer_remove(self._id)
            super(Timer, self).unregister()


    def get_interval(self):
        return self._interval


    def __call__(self, *args, **kwargs):
        if not self.active():
            # This happens if previous timer that has been called during the
            # same notifier step has stopped us. The new notifier could
            # should prevent this.
            log.error('calling callback on inactive timer (%s)' % repr(self))
            return False

        return super(Timer, self).__call__(*args, **kwargs)


class OneShotTimer(Timer):
    """
    A Timer that only gets executed once. If the timer is started again
    inside the callback, make sure 'False' is NOT returned or the timer
    will be removed again without being called. To be on tge same side,
    return nothing in such a callback.
    """
    def __call__(self, *args, **kwargs):
        self.unregister()
        super(Timer, self).__call__(*args, **kwargs)
        return False



class WeakTimer(notifier.WeakNotifierCallback, Timer):
    pass

class WeakOneShotTimer(notifier.WeakNotifierCallback, OneShotTimer):
    pass

class OneShotAtTimer(OneShotTimer):
    """
    Timer that will get executed at a time specified with a list
    of hours, minutes and seconds.
    """
    def schedule(self, hour=range(24), min=range(60), sec=0):
        if not isinstance(hour, (list, tuple)):
            hour = [ hour ]
        if not isinstance(min, (list, tuple)):
            min = [ min ]
        if not isinstance(sec, (list, tuple)):
            sec = [ sec ]
        self._timings = [ ( 5, sec), (4, min), (3, hour) ]
        self._schedule_next()


    def _schedule_next(self):
        """
        Internal function to calculate the next callback time and
        schedule it.
        """
        ctime = time.time()
        next = list(time.localtime(ctime))
        for pos, values in self._timings:
            for v in values:
                if v > next[pos]:
                    next[pos] = v
                    self.start(time.mktime(next) - ctime)
                    return
            next[pos] = values[0]
        self.start(time.mktime(next + 24 * 60 * 60) - ctime)


class AtTimer(OneShotAtTimer):
    """
    Timer that will get executed at a time specified with a list
    of hours, minutes and seconds. The timer will run until the
    callback returns False or 'stop' is called.
    """
    def __call__(self, *args, **kwargs):
        if super(Timer, self).__call__(*args, **kwargs) != False:
            self._schedule_next()
