# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# decorators.py - Some helping decorators based on kaa.notifier
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# kaa.notifier - Mainloop and callbacks
# Copyright (C) 2006-2008 Dirk Meyer, Jason Tackaberry, et al.
#
# First Version: Dirk Meyer <dmeyer@tzi.de>
# Maintainer:    Dirk Meyer <dmeyer@tzi.de>
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

__all__ = [ 'timed', 'threaded', 'MAINTHREAD', 'POLICY_ONCE', 'POLICY_MANY',
            'POLICY_RESTART' ]

# python imports
import logging

# notifier thread imports
from thread import MainThreadCallback, ThreadCallback, is_mainthread
from jobserver import NamedThreadCallback
from timer import Timer
from kaa.weakref import weakref

MAINTHREAD = object()
POLICY_ONCE = 'once'
POLICY_MANY = 'many'
POLICY_RESTART = 'restart'

# get logging object
log = logging.getLogger('notifier')

def timed(interval, timer=Timer, policy=POLICY_MANY):
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
                t = timer(func, *args, **kwargs)
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
            t = timer(func, *args, **kwargs)
            setattr(obj, name, weakref(t))
            getattr(obj, name).start(interval)
            return True

        newfunc.func_name = func.func_name
        return newfunc

    return decorator


def threaded(name=None, priority=0, async=True):
    """
    The decorator makes sure the function is always called in the thread
    with the given name. The function will return an InProgress object if
    async=True (default), otherwise it will cause invoking the decorated
    function to block (the main loop is kept alive) and its result is
    returned.

    If name=kaa.MAINTHREAD, the decorated function will be invoked from
    the main thread.  (In this case, currently the priority kwarg is
    ignored.)
    """
    def decorator(func):

        def newfunc(*args, **kwargs):
            if name is MAINTHREAD:
                if not async and is_mainthread():
                    # Fast-path case: mainthread synchronous call from the mainthread
                    return func(*args, **kwargs)
                callback =  MainThreadCallback(func)
            elif name:
                callback = NamedThreadCallback((name, priority), func)
            else:
                callback = ThreadCallback(func)
                callback.wait_on_exit(False)

            # callback will always return InProgress
            in_progress = callback(*args, **kwargs)
            if not async:
                return in_progress.wait()
            return in_progress

        try:
            newfunc.func_name = func.func_name
        except TypeError:
            pass
        return newfunc

    return decorator
