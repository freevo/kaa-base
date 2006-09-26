# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# callback.py - Callback classes for the notifier
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# kaa.notifier - Mainloop and callbacks
# Copyright (C) 2005, 2006 Dirk Meyer, Jason Tackaberry, et al.
#
# First Version: Dirk Meyer <dmeyer@tzi.de>
# Maintainer:    Dirk Meyer <dmeyer@tzi.de>
#                Jason Tackaberry <tack@sault.org>
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

__all__ = [ 'Callback', 'WeakCallback', 'Signal' ]

# Python imports
import _weakref
import types
import sys
import logging
import atexit

# get logging object
log = logging.getLogger('notifier')

# Variable that is set to True (via atexit callback) when python interpreter
# is in the process of shutting down.  If we're interested if the interpreter
# is shutting down, we don't want to test that this variable is True, but
# rather that it is not False, because as it is prefixed with an underscore,
# the interpreter might already have deleted this variable in which case it
# is None.
_python_shutting_down = False


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

        self._entered = True
        result = cb(*cb_args, **cb_kwargs)
        self._entered = False
        return result


    def __repr__(self):
        """
        Convert to string for debug.
        """
        return '<%s for %s>' % (self.__class__.__name__, self._callback)


    def __deepcopy__(self, memo):
        """
        Disable deepcopying because deepcopy can't deal with callables.
        """
        return None

    def __cmp__(self, func):
        """
        Compares the given function with the callback function we're wrapping.
        """
        return cmp(id(self), id(func)) or cmp(self._get_callback(), func)


class NotifierCallback(Callback):

    def __init__(self, callback, *args, **kwargs):
        super(NotifierCallback, self).__init__(callback, *args, **kwargs)
        self._id = None

        self.signals = {
            "exception": Signal(),
            "unregistered": Signal()
        }


    def active(self):
        # callback is active if id is not None and python is not shutting down
        # if python is in shutdown, notifier unregister could crash
        return self._id != None and _python_shutting_down == False


    def unregister(self):
        # Unregister callback with notifier.  Must be implemented by subclasses.
        self.signals["unregistered"].emit()
        self._id = None


    def __call__(self, *args, **kwargs):
        if not self._get_callback():
            if self.active():
                self.unregister()
            return False

        # If there are exception handlers for this notifier callback, we
        # catch the exception and pass it to the handler, giving it the
        # opportunity to abort the unregistering.  If no handlers are
        # attached and an exception is raised, it will be propagated up to
        # our caller.
        if self.signals["exception"].count() > 0:
            try:
                ret = super(NotifierCallback, self).__call__(*args, **kwargs)
            except:
                # If any of the exception handlers return True, then the
                # object is not unregistered from the Notifier.  Otherwise
                # ret = False and it will unregister.
                ret = self.signals["exception"].emit(sys.exc_info()[1])
        else:
            ret = super(NotifierCallback, self).__call__(*args, **kwargs)
        # If Notifier callbacks return False, they get unregistered.
        if ret == False:
            self.unregister()
            return False
        return True


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


    def __repr__(self):
        if self._instance and self._instance():
            name = "method %s of %s" % (self._callback, self._instance())
        else:
            name = self._callback
        return '<%s for %s>' % (self.__class__.__name__, name)

    def _get_callback(self):
        if self._instance:
            if self._instance() != None:
                return getattr(self._instance(), self._callback)
        else:
            return self._callback


    def __call__(self, *args, **kwargs):
        if _python_shutting_down != False:
            # Shutdown
            return False

        save_args, save_kwargs = self._args, self._kwargs

        # Remove weakrefs from user data before invoking the callback.
        self._args = unweakref_data(self._args)
        self._kwargs = unweakref_data(self._kwargs)

        result = super(WeakCallback, self).__call__(*args, **kwargs)

        self._args, self._kwargs = save_args, save_kwargs

        return result


    def set_weakref_destroyed_cb(self, callback):
        self._weakref_destroyed_user_cb = callback


    def _weakref_destroyed(self, object):
        if _python_shutting_down != False:
            # Shutdown
            return
        try:
            if self._weakref_destroyed_user_cb:
                return self._weakref_destroyed_user_cb(object)
        except:
            log.exception("Exception raised during weakref destroyed callback")



class WeakNotifierCallback(WeakCallback, NotifierCallback):

    def _weakref_destroyed(self, object):
        if _python_shutting_down == False:
            super(WeakNotifierCallback, self)._weakref_destroyed(object)
            self.unregister()


class Signal(object):

    # Parameters for changed callback
    SIGNAL_CONNECTED = 1
    SIGNAL_DISCONNECTED = 2

    def __init__(self, changed_cb = None):
        self._callbacks = []
        self._changed_cb = changed_cb


    def __iter__(self):
        for cb in self._callbacks:
            cb_callback, cb_args, cb_kwargs, cb_once, cb_weak = cb
            if cb_weak:
                cb_callback = cb_callback._get_callback()

            yield cb_callback


    def __len__(self):
        return len(self._callbacks)


    def __contains__(self, key):
        if not callable(key):
            return False

        for cb in self._callbacks:
            cb_callback, cb_args, cb_kwargs, cb_once, cb_weak = cb
            if cb_weak:
                cb_callback = cb_callback._get_callback()
            if cb_callback == key:
                return True

        return False

    def _connect(self, callback, args = (), kwargs = {}, once = False,
                 weak = False, pos = -1):

        assert(callable(callback))

        if len(self._callbacks) > 40:
            # It's a common problem (for me :)) that callbacks get added
            # inside another callback.  This is a simple sanity check.
            print "Signal callbacks exceeds 40.  Something's wrong!"
            print callback, args
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
        assert(callable(callback))
        new_callbacks = []
        for cb in self._callbacks[:]:
            cb_callback, cb_args, cb_kwargs, cb_once, cb_weak = cb
            if cb_weak:
                cb_callback_u = cb_callback._get_callback()
                cb_args_u, cb_kwargs_u = unweakref_data((cb_args, cb_kwargs))
            else:
                cb_callback_u = cb_args_u = cb_kwargs_u = None

            if (callback in (cb_callback, cb_callback_u) and len(args) == 0) or \
               (cb_callback, cb_args, cb_kwargs) == (callback, args, kwargs) or \
               (cb_callback_u, cb_args_u, cb_kwargs_u) == (callback, args, kwargs):
                # This matches what we want to disconnect.
                continue

            new_callbacks.append(cb)

        if len(new_callbacks) != len(self._callbacks):
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
        """
        Emits the signal, passing the args and kwargs to each signal handler.
        The default return value is True, but if any of the signal handlers
        return False, this method will return False.
        """
        if len(self._callbacks) == 0:
            return True

        retval = True
        for cb_callback, cb_args, cb_kwargs, cb_once, cb_weak in self._callbacks[:]:
            if cb_weak:
                cb_callback_u = cb_callback._get_callback()
                if cb_callback_u == None:
                    # A reference died while we were in the process of
                    # emitting this signal.  This callback should already be
                    # disconnected, but since we're working on a copy we will
                    # encounter it.
                    continue

                cb_callback = cb_callback_u
                cb_args, cb_kwargs = unweakref_data((cb_args, cb_kwargs))
            else:
                cb_kwargs = cb_kwargs.copy()

            if cb_once:
                self.disconnect(cb_callback, *cb_args, **cb_kwargs)
            cb_kwargs.update(kwargs)
            try:
                if cb_callback(*(args + cb_args), **cb_kwargs) == False:
                    retval = False
            except (KeyboardInterrupt, SystemExit):
                raise SystemExit
            except Exception, e:
                log.exception('signal.emit')
        return retval


    def _weakref_destroyed(self, callback, weakref):
        if _python_shutting_down == False:
            self._disconnect(callback, (), None)


    def count(self):
        return len(self._callbacks)


def _shutdown_weakref_destroyed():
    global _python_shutting_down
    _python_shutting_down = True

atexit.register(_shutdown_weakref_destroyed)
