# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# signals.py - Signal object
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

__all__ = [ 'Signal', 'Signals' ]

# Python imports
import logging
import atexit

# callbacks from kaa.notifier
from callback import Callback, WeakCallback
from kaa.utils import property

# get logging object
log = logging.getLogger('notifier')

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
        if self._changed_cb:
            self._changed_cb(self, Signal.SIGNAL_CONNECTED)

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
            print "weakref destroyed, disconnecting", self
            self._disconnect(callback, (), {})


    def count(self):
        return len(self._callbacks)


    def async(self):
        """
        Convenience function which returns an InProgressCallback for this
        signal.  The returned InProgress object is finished when this signal is
        emitted.

        For example, if you want to block while waiting for the signal to be
        emitted from another thread or coroutine, you could do::

           signal.async().wait()

        """
        from async import InProgressCallback
        # Have the InProgress callback connect weakly to us, so that if it
        # goes away the callback is automatically disconnected.
        return InProgressCallback(self.connect_weak_once)


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


    def add(self, *signals):
        """
        Creates a new Signals object by merging all signals defined in
        self and the signals specified in the arguments.
        """
        return Signals(self, *signals)


    def subset(self, *names):
        """
        Returns a new Signals object by taking a subset of the supplied
        signals.

            >>> yield signals.subset('pass', 'fail).any()
        """
        return Signals(dict([(k, self[k]) for k in names]))


    def any(self):
        """
        Returns an InProgressAny object with all signals in self.
        """
        from async import InProgressAny
        return InProgressAny(*[s.async() for s in self.values()])
        

    def all(self):
        """
        Returns an InProgressAll object with all signals in self.
        """
        from async import InProgressAll
        return InProgressAll(*[s.async() for s in self.values()])


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
