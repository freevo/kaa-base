# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# callback.py - Callback classes for the notifier
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

__all__ = [ 'Callback', 'WeakCallback', 'Timer', 'WeakTimer', 'OneShotTimer',
            'WeakOneShotTimer', 'SocketDispatcher', 'WeakSocketDispatcher' ]

import weakref

try:
    # try to import pyNotifier
    import notifier
    # init pyNotifier with the generic notifier
    notifier.init(notifier.GENERIC)
    use_pynotifier = True

except ImportError:
    # use a copy of nf_generic
    import nf_generic as notifier
    use_pynotifier = False

IO_READ   = notifier.IO_READ
IO_WRITE  = notifier.IO_WRITE
IO_EXCEPT = notifier.IO_EXCEPT

def select_notifier(type):
    """
    Select a new notifier.
    """
    if not use_pynotifier:
        raise AttributeError('pyNotifier not installed')
    if type == notifier.GENERIC:
        raise AttributeError('generic notifier already running')
    notifier.init(type)

    global IO_READ
    global IO_WRITE
    global IO_EXCEPT

    IO_READ   = notifier.IO_READ
    IO_WRITE  = notifier.IO_WRITE
    IO_EXCEPT = notifier.IO_EXCEPT



class Callback(object):
    """
    Wrapper for functions calls with arguments inside the notifier. The
    function passed to this objects get the parameter passed to this object
    and after that the args and kwargs defined in the init function.
    """
    def __init__(self, callback, *args, **kwargs):
        assert(callable(callback))
        self._callback = callback
        self._args = args
        self._kwargs = kwargs
        self._ignore_caller_args = False
        self._user_args_first = False


    def set_ignore_caller_args(self, flag = True):
        self._ignore_caller_args = flag


    def set_user_args_first(self, flag = True):
        self._user_args_first = flag


    def _get_callback(self):
        return self._callback


    def __call__(self, *args, **kwargs):
        """
        Call the callback function.
        """
        cb = self._get_callback()
        if not cb:
            # Is it wise to fail so gracefully here?
            return

        if self._ignore_caller_args:
            cb_args, cb_kwargs = self._args, self._kwargs
        else:
            if self._user_args_first:
                cb_args, cb_kwargs = self._args + args, kwargs
                cb_kwargs.update(self._kwargs)
            else:
                cb_args, cb_kwargs = args + self._args, self._kwargs
                cb_kwargs.update(kwargs)
            
        return cb(*cb_args, **cb_kwargs)



class NotifierCallback(Callback):
    
    def __init__(self, callback, *args, **kwargs):
        super(NotifierCallback, self).__init__(callback, *args, **kwargs)
        self._id = None

           
    def active(self):
        return self._id != None


    def unregister(self):
        # Unregister callback with notifier.  Must be implemented by subclasses.
        self._id = None


    def __call__(self, *args, **kwargs):
        if not self._get_callback():
            if self.active():
                self.unregister()
            return False

        ret = super(NotifierCallback, self).__call__(*args, **kwargs)
        # If Notifier callbacks return False, they get unregistered.
        if ret == False:
            self.unregister()
            return False
        return True



class Timer(NotifierCallback):

    def start(self, interval):
        if self.active():
            self.unregister()
        self._id = notifier.addTimer(interval, self)


    def stop(self):
        self.unregister()


    def unregister(self):
        if self.active():
            notifier.removeTimer(self._id)
            self._id = None



class OneShotTimer(Timer):

    def __call__(self, *args, **kwargs):
        self.unregister()
        super(OneShotTimer, self).__call__(*args, **kwargs)
        return False



class SocketDispatcher(NotifierCallback):

    def __init__(self, callback, *args, **kwargs):
        super(SocketDispatcher, self).__init__(callback, *args, **kwargs)
        self.set_ignore_caller_args()


    def register(self, fd, condition = None):
        if self.active():
            return

        if condition == None:
            self._id = notifier.addSocket(fd, self)
        else:
            self._id = notifier.addSocket(fd, self, condition)


    def unregister(self):
        if self.active():
            notifier.removeSocket(self._id)
            self._id = None



class WeakCallback(Callback):

    def __init__(self, callback, *args, **kwargs):
        super(WeakCallback, self).__init__(callback, *args, **kwargs)
        if hasattr(callback, "im_self"):
            # For methods
            self._instance = weakref.ref(callback.im_self, self._weakref_destroyed)
            self._callback = callback.im_func.func_name
        else:
            # No need to weakref functions.  (If we do, we can't use closures.)
            self._instance = None

        # TODO: make weak refs of args/kwargs too.


    def _get_callback(self):
        if self._instance:
            if self._instance():
                return getattr(self._instance(), self._callback)
        else:
            return self._callback


    def _weakref_destroyed(self, object):
        pass



class WeakNotifierCallback(WeakCallback, NotifierCallback):

    def _weakref_destroyed(self, object):
        self.unregister()


class WeakTimer(WeakNotifierCallback, Timer):
    pass

class WeakOneShotTimer(WeakNotifierCallback, OneShotTimer):
    pass

class WeakSocketDispatcher(WeakNotifierCallback, SocketDispatcher):
    pass



