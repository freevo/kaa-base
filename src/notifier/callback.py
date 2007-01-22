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

__all__ = [ 'Callback', 'WeakCallback', 'Signal', 'Signals' ]

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
    if type(data) in (str, int, long, types.NoneType, types.FunctionType):
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
    else:
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


    def get_user_args(self):
        return self._args, self._kwargs


    def _get_callback(self):
        return self._callback


    def _merge_args(self, args, kwargs):
        user_args, user_kwargs = self.get_user_args()
        if self._ignore_caller_args:
            cb_args, cb_kwargs = user_args, user_kwargs
        else:
            if self._user_args_first:
                cb_args, cb_kwargs = user_args + args, kwargs
                cb_kwargs.update(user_kwargs)
            else:
                cb_args, cb_kwargs = args + user_args, user_kwargs
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

    def __eq__(self, func):
        """
        Compares the given function with the callback function we're wrapping.
        """
        return id(self) == id(func) or self._get_callback() == func


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
            self._instance = None
            # Don't weakref lambdas.
            if not hasattr(callback, 'func_name') or callback.func_name != '<lambda>':
                self._callback = _weakref.ref(callback, self._weakref_destroyed)

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
        elif isinstance(self._callback, _weakref.ReferenceType):
            return self._callback()
        else:
            return self._callback

    def get_user_args(self):
        return unweakref_data(self._args), unweakref_data(self._kwargs)

    def __call__(self, *args, **kwargs):
        if _python_shutting_down != False:
            # Shutdown
            return False

        return super(WeakCallback, self).__call__(*args, **kwargs)


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
            yield cb


    def __len__(self):
        return len(self._callbacks)


    def __nonzero__(self):
        return True


    def __contains__(self, key):
        if not callable(key):
            return False

        for cb in self._callbacks:
            if cb == key:
                return True

        return False

    def _connect(self, callback, args = (), kwargs = {}, once = False, weak = False, pos = -1):
        """
        Connects a new callback to the signal.  args and kwargs will be bound
        to the callback and merged with the args and kwargs passed during 
        emit().  If weak is True, a WeakCallback will be created.  If once is
        True, the callback will be automatically disconnected after the next
        emit().

        This method returns the Callback (or WeakCallback) object created.
        """

        assert(callable(callback))

        if len(self._callbacks) > 40:
            # It's a common problem (for me :)) that callbacks get added
            # inside another callback.  This is a simple sanity check.
            log.error("Signal callbacks exceeds 40.  Something's wrong!")
            log.error("%s: %s", callback, args)
            raise Exception("Signal callbacks exceeds 40")

        if weak:
            callback = WeakCallback(callback, *args, **kwargs)
            # We create a callback for weakref destruction for both the
            # signal callback as well as signal data.
            destroy_cb = Callback(self._weakref_destroyed, callback)
            callback.set_weakref_destroyed_cb(destroy_cb)
        else:
            callback = Callback(callback, *args, **kwargs)

        callback._signal_once = once

        if pos == -1:
            pos = len(self._callbacks)

        self._callbacks.insert(pos, callback)
        if self._changed_cb:
            self._changed_cb(self, Signal.SIGNAL_CONNECTED)
        return callback


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
            if cb == callback and (len(args) == len(kwargs) == 0 or (args, kwargs) == cb.get_user_args()):
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
        for cb in self._callbacks[:]:
            if cb._signal_once:
                self.disconnect(cb)

            try:
                if cb(*args, **kwargs) == False:
                    retval = False
            except (KeyboardInterrupt, SystemExit):
                raise SystemExit
            except Exception, e:
                log.exception('signal.emit')
        return retval


    def _weakref_destroyed(self, weakref, callback):
        if _python_shutting_down == False:
            self._disconnect(callback, (), {})

    def count(self):
        return len(self._callbacks)


class Signals(dict):
    """
    Dict of Signal object.
    """
    def __init__(self, *signals):
        dict.__init__(self)
        for s in signals:
            if isinstance(s, dict):
                # parameter is a dict/Signals object
                self.update(s)
            elif isinstance(s, str):
                # parameter is a string
                self[s] = Signal()
            else:
                # parameter is something else, bad
                raise AttributeError('signal key must be string')

            
    def __getattr__(self, attr):
        """
        Get attribute function from Signal().
        """
        if attr.startswith('_') or not hasattr(Signal, attr):
            return dict.__getattr__(self, attr)
        callback = Callback(self._callattr, attr)
        callback.set_user_args_first(True)
        return callback

    
    def _callattr(self, attr, signal, *args, **kwargs):
        """
        Call attribute function from Signal().
        """
        return getattr(self[signal], attr)(*args, **kwargs)


def _shutdown_weakref_destroyed():
    global _python_shutting_down
    _python_shutting_down = True

atexit.register(_shutdown_weakref_destroyed)
