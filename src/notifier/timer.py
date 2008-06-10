# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# timer.py - Timer classes for the notifier
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# kaa.notifier - Mainloop and callbacks
# Copyright (C) 2005-2008 Dirk Meyer, Jason Tackaberry, et al.
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
            'AtTimer', 'OneShotAtTimer', 'POLICY_ONCE', 'POLICY_MANY', 
            'POLICY_RESTART' ]

import logging
import datetime

import nf_wrapper as notifier
from thread import threaded, MAINTHREAD
from kaa.weakref import weakref

POLICY_ONCE = 'once'
POLICY_MANY = 'many'
POLICY_RESTART = 'restart'

# get logging object
log = logging.getLogger('notifier')


def timed(interval, timer=None, policy=POLICY_MANY):
    """
    Decorator to call the decorated function in a Timer. When calling the
    function, a timer will be started with the given interval calling that
    function.  The decorated function will be called from the main thread.

    The timer parameter optionally specifies which timer class should be
    used to wrap the function.  kaa.Timer (default) or kaa.WeakTimer will
    repeatedly invoke the decorated function until it returns False.
    kaa.OneShotTimer or kaa.WeakOneShotTimer will invoke the function once,
    delaying it by the specified interval.  (In this case the return value
    of the decorated function is irrelevant.)

    The policy parameter controls how multiple invocations of the decorated
    function should be handled.  By default (POLICY_MANY), each invocation of
    the function will create a new timer, each firing at the specified
    interval.  If policy is POLICY_ONCE, subsequent invocations are ignored
    while the first timer is still active.  If the policy is POLICY_RESTART,
    subsequent invocations will restart the first timer.

    Note that in the case of POLICY_ONCE or POLICY_RESTART, if the timer is
    currently running, any arguments passed to the decorated function on
    subsequent calls will be discarded.
    """
    if not policy in (POLICY_MANY, POLICY_ONCE, POLICY_RESTART):
        raise RunTimeError('Invalid @kaa.timed policy %s' % policy)

    def decorator(func):
        def newfunc(*args, **kwargs):
            if policy == POLICY_MANY:
                # just start the timer
                t = (timer or Timer)(func, *args, **kwargs)
                t.start(interval)
                return True

            # Object to save the timer in; the function itself for non-methods,
            # or the instance object for methods.
            # object to save the timer in
            obj = func
            # name of the attribute in the object
            name = '__kaa_timer_decorator'

            # Try to find out if the function is actually an instance method.
            # The decorator only sees a function object, even for methods, so
            # this kludge compares the code object of newfunc (this wrapper)
            # with the code object of the first argument's attribute of the
            # function's name.  If they're the same, then we must be decorating
            # a method, and we can attach the timer object to the instance
            # instead of the function.
            if args and newfunc.func_code == \
                        getattr(getattr(args[0], func.func_name, None), 'func_code', None):
                obj  = args[0]
                name = '%s__%s' % (name, func.func_name)

            # check current timer
            if getattr(obj, name, None) and getattr(obj, name).active():
                if policy == POLICY_ONCE:
                    # timer already running and not override
                    return False
                # stop old timer
                getattr(obj, name).stop()

            # create new timer, set it to the object and start it
            t = (timer or Timer)(func, *args, **kwargs)
            setattr(obj, name, weakref(t))
            getattr(obj, name).start(interval)
            return True

        newfunc.func_name = func.func_name
        return newfunc

    return decorator



class Timer(notifier.NotifierCallback):

    def __init__(self, callback, *args, **kwargs):
        super(Timer, self).__init__(callback, *args, **kwargs)
        self.restart_when_active = True
        self._interval = None


    @threaded(MAINTHREAD)
    def start(self, interval):
        """
        Start the timer.
        @param interval: interval in seconds
        @note: this function will always be called from the mainthread
        """
        if self.active():
            if not self.restart_when_active:
                return
            self.unregister()

        self._id = notifier.timer_add(int(interval * 1000), self)
        self._interval = interval


    @threaded(MAINTHREAD)
    def stop(self):
        """
        Stop a running timer.
        @note: this function will always be called from the mainthread
        """
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
    def start(self, hour=range(24), min=range(60), sec=0):
        if not isinstance(hour, (list, tuple)):
            hour = [ hour ]
        if not isinstance(min, (list, tuple)):
            min = [ min ]
        if not isinstance(sec, (list, tuple)):
            sec = [ sec ]

        self._timings = hour, min, sec
        self._last_time = datetime.datetime.now()
        self._schedule_next()


    def _schedule_next(self):
        """
        Internal function to calculate the next callback time and
        schedule it.
        """
        hour, min, sec = self._timings
        now = datetime.datetime.now()
        # Take the later of now or the last scheduled time for purposes of
        # determining the next time.  If we use the current system time
        # instead, we may end up firing a callback twice for a given time,
        # because due to imprecision we may end up here slightly before (a few
        # milliseconds) the scheduled time.
        t = max(self._last_time, now).replace(microsecond = 0)

        next_sec = [ x for x in sec if t.second < x ]
        next_min = [ x for x in min if t.minute < x ]
        next_hour = [ x for x in hour if t.hour < x ]

        if next_sec:
            next = t.replace(second = next_sec[0])
        elif next_min:
            next = t.replace(minute = next_min[0], second = sec[0])
        elif next_hour:
            next = t.replace(hour = next_hour[0], minute = min[0], second = sec[0])
        else:
            tmrw = t + datetime.timedelta(days = 1)
            next = tmrw.replace(hour = hour[0], minute = min[0], second = sec[0])

        delta = next - now
        super(OneShotAtTimer, self).start(delta.seconds + delta.microseconds / 1000000.0)
        self._last_time = next


class AtTimer(OneShotAtTimer):
    """
    Timer that will get executed at a time specified with a list
    of hours, minutes and seconds. The timer will run until the
    callback returns False or 'stop' is called.
    """
    def __call__(self, *args, **kwargs):
        if super(Timer, self).__call__(*args, **kwargs) != False:
            self._schedule_next()
