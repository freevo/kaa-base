# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# callback.py - Callback classes for the notifier
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

__all__ = [ 'Callback', 'WeakCallback' ]

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



def _shutdown_weakref_destroyed():
    global _python_shutting_down
    _python_shutting_down = True

atexit.register(_shutdown_weakref_destroyed)
