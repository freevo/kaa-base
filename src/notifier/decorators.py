# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# decorators.py - Some helping decorators based on kaa.notifier
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
# Please see the file AUTHORS for a complete list of authors.
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

__all__ = [ 'execute_in_timer', 'execute_in_mainloop' ]

# python imports
import logging

# notifier thread imports
from thread import MainThreadCallback, is_mainthread
from kaa.weakref import weakref
from yieldfunc import InProgress

# get logging object
log = logging.getLogger('notifier')

def execute_in_timer(timer, interval, type=''):
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
                t.set_prevent_recursion()
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
            t.set_prevent_recursion()
            setattr(obj, name, weakref(t))
            getattr(obj, name).start(interval)
            return True

        newfunc.func_name = func.func_name
        return newfunc

    return decorator


def execute_in_mainloop(async=False):
    """
    This decorator makes sure the function is called from the main loop. If
    the calling thread is the mainloop, it is a normal function call, if not,
    MainThreadCallback is used to call the function. If 'async' is set to False,
    the thread will wait for the answer. It is possible with this decorator to
    have a longer codeblock in a thread and call functions not thread save.
    """
    def decorator(func):

        def newfunc(*args, **kwargs):
            if is_mainthread():
                return func(*args, **kwargs)
            t = MainThreadCallback(func, *args, **kwargs)
            t.set_async(async)
            return t()

        try:
            newfunc.func_name = func.func_name
        except TypeError:
            pass
        return newfunc

    return decorator
