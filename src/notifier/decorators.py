# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# decorators.py - Some helping decorators based on kaa.notifier
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# kaa.notifier - Mainloop and callbacks
# Copyright (C) 2006 Dirk Meyer, Jason Tackaberry, et al.
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

__all__ = [ 'timed', 'threaded', 'MAINTHREAD' ]

# python imports
import logging

# notifier thread imports
from thread import MainThreadCallback, ThreadCallback, is_mainthread
from jobserver import NamedThreadCallback
from kaa.weakref import weakref

MAINTHREAD = 'main'

# get logging object
log = logging.getLogger('notifier')

def timed(timer, interval, type=''):
    """
    Decorator to call the decorated function in a Timer. When calling the
    function, a timer will be started with the given interval calling that
    function. This decorater is usefull for putting a huge task into smaller
    once calling each task in one step of the main loop or execute a function
    delayed. The parameter timer is the timer class to use (Timer or WeakTimer
    for stepping or OneShotTimer or WeakOneShotTimer for delayed). The parameter
    type can be used to force having only one timer active at one time. Set
    type to 'once' to make sure only the first active timer is executed, a
    later one will be ignored or 'override' to remove the current timer and
    activate the new call. If you use 'once' or 'override', keep in mind that
    if you call the function with different parameters only one call gets
    executed.
    """

    if not type in ('', 'once', 'override'):
        raise RunTimeError('invalid type %s' % type)

    def decorator(func):

        def newfunc(*args, **kwargs):
            if not type:
                # just start the timer
                t = timer(func, *args, **kwargs)
                t.start(interval)
                return True
            # object to save the timer in
            obj  = func
            # name of the attribute in the object
            name = '__kaa_timer_decorator'
            # Try to find out if the function is bound to an object.
            # FIXME: maybe this is bad solution, how fast is comparing
            # the func_code attributes?
            if args and args[0] and hasattr(args[0], func.func_name) and \
                   newfunc.func_code == getattr(args[0], func.func_name).func_code:
                obj  = args[0]
                name = '%s__%s' % (name, func.func_name)
            # check current timer
            if hasattr(obj, name) and getattr(obj, name) and \
                   getattr(obj, name).active():
                if type == 'once':
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
            if name == MAINTHREAD:
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
