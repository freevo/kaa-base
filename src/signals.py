# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# signals.py - Signal object
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# kaa.base - The Kaa Application Framework
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

__all__ = [ 'Signal', 'Signals' ]

# Python imports
import logging
import atexit

# kaa imports
from callback import Callback, WeakCallback
from utils import property

# Recursive import. async itself exists, but not the async.InProgress*
# objects we need. When we need to access them, they are available.
import async

# get logging object
log = logging.getLogger('base')

# Variable that is set to True (via atexit callback) when python interpreter
# is in the process of shutting down.  If we're interested if the interpreter
# is shutting down, we don't want to test that this variable is True, but
# rather that it is not False, because as it is prefixed with an underscore,
# the interpreter might already have deleted this variable in which case it
# is None.
_python_shutting_down = False


class Signal(object):

    # Parameters for changed callback
    SIGNAL_CONNECTED = 1
    SIGNAL_DISCONNECTED = 2

    def __init__(self, changed_cb = None):
        self._callbacks = []
        self.changed_cb = changed_cb
        self._deferred_args = []


    @property
    def changed_cb(self):
        return self._changed_cb


    @changed_cb.setter
    def changed_cb(self, callback):
        assert(callback is None or callable(callback))
        self._changed_cb = callback


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
        self._changed(Signal.SIGNAL_CONNECTED)

        if self._deferred_args:
            for args, kwargs in self._deferred_args:
                self.emit(*args, **kwargs)
            del self._deferred_args[:]

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

    def connect_first_once(self, callback, *args, **kwargs):
        return self._connect(callback, args, kwargs, once = True, pos = 0)

    def connect_weak_first_once(self, callback, *args, **kwargs):
        return self._connect(callback, args, kwargs, weak = True, once = True, pos = 0)

    def _disconnect(self, callback, args, kwargs):
        assert(callable(callback))
        new_callbacks = []
        for cb in self._callbacks[:]:
            if cb == callback and (len(args) == len(kwargs) == 0 or (args, kwargs) == cb._get_user_args()):
                # This matches what we want to disconnect.
                continue
            new_callbacks.append(cb)

        if len(new_callbacks) != len(self._callbacks):
            self._callbacks = new_callbacks
            self._changed(Signal.SIGNAL_DISCONNECTED)
            return True

        return False


    def _changed(self, action):
        """
        Called when a callback was connected or disconnected.

        @param action: SIGNAL_CONNECTED or SIGNAL_DISCONNECTED.
        """
        if self._changed_cb:
            self._changed_cb(self, action)


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
                raise
            except Exception, e:
                log.exception('signal.emit')
        return retval


    def emit_deferred(self, *args, **kwargs):
        """
        Queues the emission until after the next callback is connected.  This
        allows a signal to be 'primed' by its creator, and the handler that
        subsequently connects to it will be called with the given arguments.
        """
        self._deferred_args.append((args, kwargs))


    def emit_when_handled(self, *args, **kwargs):
        """
        Emits the signal if there are callbacks connected, or defer it until
        the first callback is connected.
        """
        if self.count():
            return self.emit(*args, **kwargs)
        else:
            self.emit_deferred(*args, **kwargs)


    def _weakref_destroyed(self, weakref, callback):
        if _python_shutting_down == False:
            #print "Weakref destroyed, disconnect", self, weakref, callback
            self._disconnect(callback, (), {})


    def count(self):
        return len(self._callbacks)


    def __inprogress__(self):
        """
        Returns an InProgressCallback for this signal.  The returned InProgress
        object is finished when this signal is emitted.  The InProgress is
        connected weakly to us, so when the InProgress is destroyed, the
        callback is automatically disconnected.
        """
        return async.InProgressCallback(self.connect_weak_once)



class Signals(dict):
    """
    Dict of Signal object.  This dict preserves the order of keys.
    """
    def __init__(self, *signals):
        dict.__init__(self)
        # Preserve order of keys.
        self._keys = []
        for s in signals:
            if isinstance(s, dict):
                # parameter is a dict/Signals object
                self.update(s)
                self._keys.extend(s.keys())
            elif isinstance(s, str):
                # parameter is a string
                self[s] = Signal()
                self._keys.append(s)
            elif isinstance(s, (tuple, list)) and len(s) == 2:
                # In form (key, value)
                if isinstance(s[0], basestring) and isinstance(s[1], Signal):
                    self[s[0]] = s[1]
                    self._keys.append(s[0])
                else:
                    raise TypeError('With form (k, v), key must be string and v must be Signal')

            else:
                # parameter is something else, bad
                raise TypeError('signal key must be string')


    def __delitem__(self, key):
        super(Signals, self).__delitem__(key)
        self._keys.remove(key)


    def keys(self):
        return self._keys


    def values(self):
        return [ self[k] for k in self._keys ]


    def __add__(self, signals):
        return Signals(self, *signals)


    def add(self, *signals):
        """
        Creates a new Signals object by merging all signals defined in
        self and the signals specified in the arguments.
        """
        return Signals(self, *signals)


    def subset(self, *names):
        """
        Returns a new Signals object by taking a subset of the supplied
        signals.  The keys of the new Signals object are ordered as specified
        in the names parameter.

            >>> yield signals.subset('pass', 'fail).any()
        """
        return Signals(*[(k, self[k]) for k in names])


    def any(self):
        """
        Returns an InProgressAny object with all signals in self.
        """
        return async.InProgressAny(*self.values())


    def all(self):
        """
        Returns an InProgressAll object with all signals in self.
        """
        return async.InProgressAll(*self.values())


    def __getattr__(self, attr):
        """
        Get attribute function from Signal().
        """
        if attr.startswith('_') or not hasattr(Signal, attr):
            return dict.__getattr__(self, attr)
        callback = Callback(self._callattr, attr)
        callback.user_args_first = True
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
