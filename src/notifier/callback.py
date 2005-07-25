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
            'WeakOneShotTimer', 'SocketDispatcher', 'WeakSocketDispatcher',
            'MainThreadCallback', 
            'IO_READ', 'IO_WRITE', 'IO_EXCEPT', 'notifier' ]

import _weakref
import types
import os
import threading
import kaa.notifier

try:
    # try to import pyNotifier
    import notifier
    if not notifier.loop:
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


def weakref_data(data, destroy_cb = None):
    if type(data) in (str, int, long, types.NoneType):
        # Naive optimization for common immutable cases.
        return data
    elif type(data) == types.MethodType:
        cb = WeakCallback(data)
        if destroy_cb:
            cb.set_weakref_destroyed_cb(destroy_cb)
            cb.set_ignore_caller_args()
        return cb
    elif type(data) in (list, tuple):
        d = []
        for item in data:
            d.append(weakref_data(item, destroy_cb))
        if type(data) == tuple:
            d = tuple(d)
        return d
    elif type(data) == dict:
        d = {}
        for key, val in data.items():
            d[weakref_data(key)] = weakref_data(val, destroy_cb)
        return d
    elif type(data) != types.FunctionType:
        try:
            if destroy_cb:
                return _weakref.ref(data, destroy_cb)
            return _weakref.ref(data)
        except TypeError:
            pass

    return data

def unweakref_data(data):
    if type(data) in (str, int, long, types.NoneType):
        # Naive optimization for common immutable cases.
        return data
    elif type(data) == _weakref.ReferenceType:
        return data()
    elif type(data) == WeakCallback:
        return data._get_callback()
    elif type(data) in (list, tuple):
        d = []
        for item in data:
            d.append(unweakref_data(item))
        if type(data) == tuple:
            d = tuple(d)
        return d
    elif type(data) == dict:
        d = {}
        for key, val in data.items():
            d[unweakref_data(key)] = unweakref_data(val)
        return d
    else:
        return data

# For MainThread* callbacks
_thread_notifier_pipe = os.pipe()
_thread_notifier_queue = []
_thread_notifier_lock = threading.Lock()
_thread_notifier_mainthread = threading.currentThread()


def _thread_notifier_run_queue():
    _thread_notifier_lock.acquire()
    os.read(_thread_notifier_pipe[0], 1)
    while _thread_notifier_queue:
        callback, args, kwargs = _thread_notifier_queue.pop()
        callback(*args, **kwargs)
        callback.lock.acquire(False)
        callback.lock.release()
    _thread_notifier_lock.release()



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

    def _merge_args(self, args, kwargs):
        if self._ignore_caller_args:
            cb_args, cb_kwargs = self._args, self._kwargs
        else:
            if self._user_args_first:
                cb_args, cb_kwargs = self._args + args, kwargs
                cb_kwargs.update(self._kwargs)
            else:
                cb_args, cb_kwargs = args + self._args, self._kwargs
                cb_kwargs.update(kwargs)

        return cb_args, cb_kwargs
            

    def __call__(self, *args, **kwargs):
        """
        Call the callback function.
        """
        cb = self._get_callback()
        cb_args, cb_kwargs = self._merge_args(args, kwargs)
        if not cb:
            # Is it wise to fail so gracefully here?
            return

        return cb(*cb_args, **cb_kwargs)




class MainThreadCallback(Callback):
    def __init__(self, callback, *args, **kwargs):
        super(MainThreadCallback, self).__init__(callback, *args, **kwargs)
        self.lock = threading.Lock()
        self._sync_return = None
        self.set_async()

    def set_async(self, async = True):
        self._async = async

    def __call__(self, *args, **kwargs):
        if threading.currentThread() != _thread_notifier_mainthread:
            self.lock.acquire(False)

            _thread_notifier_lock.acquire()
            _thread_notifier_queue.append((self, args, kwargs))
            if len(_thread_notifier_queue) == 1:
                os.write(_thread_notifier_pipe[1], "1")
            _thread_notifier_lock.release()

            if not self._async:
                self.lock.acquire()

            return self._sync_return
        else:
            self._sync_return = super(MainThreadCallback, self).__call__(*args, **kwargs)
            return self._sync_return



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

    def __init__(self, callback, *args, **kwargs):
        super(Timer, self).__init__(callback, *args, **kwargs)
        self.restart_when_active = True


    def start(self, interval):
        if self.active():
            if not self.restart_when_active:
                return
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


    def register(self, fd, condition = IO_READ):
        if self.active():
            return
        notifier.addSocket(fd, self, condition)
        self._id = fd


    def unregister(self):
        if self.active():
            notifier.removeSocket(self._id)
            self._id = None



class WeakCallback(Callback):

    def __init__(self, callback, *args, **kwargs):
        super(WeakCallback, self).__init__(callback, *args, **kwargs)
        if type(callback) == types.MethodType:
            # For methods
            self._instance = _weakref.ref(callback.im_self, self._weakref_destroyed)
            self._callback = callback.im_func.func_name
        else:
            # No need to weakref functions.  (If we do, we can't use closures.)
            self._instance = None

        self._args = weakref_data(args, self._weakref_destroyed)
        self._kwargs = weakref_data(kwargs, self._weakref_destroyed)
        self._weakref_destroyed_user_cb = None


    def _get_callback(self):
        if self._instance:
            if self._instance():
                return getattr(self._instance(), self._callback)
        else:
            return self._callback


    def __call__(self, *args, **kwargs):
        save_args, save_kwargs = self._args, self._kwargs
    
        if not unweakref_data:
            # Shutdown
            return False
    
        # Remove weakrefs from user data before invoking the callback.
        self._args = unweakref_data(self._args)
        self._kwargs = unweakref_data(self._kwargs)

        result = super(WeakCallback, self).__call__(*args, **kwargs)

        self._args, self._kwargs = save_args, save_kwargs
    
        return result


    def set_weakref_destroyed_cb(self, callback):
        self._weakref_destroyed_user_cb = callback


    def _weakref_destroyed(self, object):
        if self and self._weakref_destroyed_user_cb:
            return self._weakref_destroyed_user_cb(object)



class WeakNotifierCallback(WeakCallback, NotifierCallback):

    def _weakref_destroyed(self, object):
        if WeakNotifierCallback and self:
            super(WeakNotifierCallback, self)._weakref_destroyed(object)
            self.unregister()


class WeakTimer(WeakNotifierCallback, Timer):
    pass

class WeakOneShotTimer(WeakNotifierCallback, OneShotTimer):
    pass

class WeakSocketDispatcher(WeakNotifierCallback, SocketDispatcher):
    pass





class Signal(object):

    # Parameters for changed callback
    SIGNAL_CONNECTED = 1
    SIGNAL_DISCONNECTED = 2

    def __init__(self, changed_cb = None):
        self._callbacks = []
        self._changed_cb = changed_cb
        self._items = {}

    def __getitem__(self, key):
        return self._items[key]

    def __setitem__(self, key, val):
        self._items[key] = val

    def __contains__(self, key):
        return key in self._items

 
    def _connect(self, callback, args = (), kwargs = {}, once = False, 
                 weak = False, pos = -1):

        if len(self._callbacks) > 40:
            # It's a common problem (for me :)) that callbacks get added
            # inside another callback.  This is a simple sanity check.
            print "Signal callbacks exceeds 40.  Something's wrong!"
            print callback, args, self._callbacks[0][0].get_method()
            raise Exception

        if weak:
            callback = WeakCallback(callback)

            # We create a callback for weakref destruction for both the
            # signal callback as well as signal data.  The destroy callback
            # has the signal callback passed as the first parameter (because
            # set_user_args_first() is called), and WeakCallback will pass
            # the weakref object itself as the second parameter.
            destroy_cb = Callback(self._weakref_destroyed, callback)
            destroy_cb.set_user_args_first()
            callback.set_weakref_destroyed_cb(destroy_cb)

            args = weakref_data(args, destroy_cb)
            kwargs = weakref_data(kwargs, destroy_cb)
        if pos == -1:
            pos = len(self._callbacks)

        self._callbacks.insert(pos, (callback, args, kwargs, once, weak))
        if self._changed_cb:
            self._changed_cb(self, Signal.SIGNAL_CONNECTED)
        return True


    def connect(self, callback, *args, **kwargs):
        return self._connect(callback, args, kwargs)

    def connect_weak(self, callback, *args, **kwargs):
        return self._connect(callback, args, kwargs, weak = True)

    def connect_once(self, callback, *args, **kwargs):
        return self._connect(callback, args, kwargs, once = True)

    def connect_weak_once(self, callback, *args, **kwargs):
        return self._connect(callback, args, kwargs, once = True, weak = True)

    def connect_first(self, callback, *args, **kwargs):
        return self._connect(callback, args, kwargs, pos = 0)

    def connect_weak_first(self, callback, *args, **kwargs):
        return self._connect(callback, args, kwargs, weak = True, pos = 0)

    def _disconnect(self, callback, args, kwargs):
        new_callbacks = []
        for pos, cb_all in zip(range(len(self._callbacks)), self._callbacks[:]):
            cb_callback, cb_args, cb_kwargs, cb_once, cb_weak = cb_all
            if cb_weak and args != None:
                cb_callback = cb_callback._get_callback()
                cb_args, cb_kwargs = unweakref_data((cb_args, cb_kwargs))

            if (cb_callback == callback and args == None) or \
               (cb_callback, cb_args, cb_kwargs) == (callback, args, kwargs):
                # This matches what we want to disconnect.
                continue

            new_callbacks.append(cb_all)

        if len(new_callbacks) != self._callbacks:
            self._callbacks = new_callbacks
            if self._changed_cb:
                self._changed_cb(self, Signal.SIGNAL_DISCONNECTED)

            return True

        return False


    def disconnect(self, callback, *args, **kwargs):
        return self._disconnect(callback, args, kwargs)


    def disconnect_all(self):
        count = self.count()
        self._callbacks = []
        if self._changed_cb and count > 0:
            self._changed_cb(self, Signal.SIGNAL_DISCONNECTED)

    def emit(self, *args, **kwargs):
        retval = False
        for cb_callback, cb_args, cb_kwargs, cb_once, cb_weak in self._callbacks[:]:
            if cb_weak:
                cb_callback = cb_callback._get_callback()
                cb_args, cb_kwargs = unweakref_data((cb_args, cb_kwargs))
            else:
                cb_kwargs = cb_kwargs.copy()

            cb_kwargs.update(kwargs)
            if cb_callback(*(args + cb_args), **cb_kwargs):
                retval = True
            if cb_once:
                self.disconnect(cb_callback, cb_args, cb_kwargs)


    def _weakref_destroyed(self, callback, weakref):
        if Signal and self:
            self._disconnect(callback, None, None)


    def count(self):
        return len(self._callbacks)



thread_monitor = SocketDispatcher(_thread_notifier_run_queue)
thread_monitor.register(_thread_notifier_pipe[0])
