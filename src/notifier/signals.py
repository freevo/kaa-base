# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# signals.py - Signal mechanism for invoking callbacks.
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# kaa-notifier - Notifier Wrapper
# Copyright (C) 2005 Dirk Meyer, et al.
#
# First Version: Jason Tackaberry <tack@sault.org>
# Maintainer:    Jason Tackaberry <tack@sault.org>
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

# FIXME: this class is a drop-in from MeBox.  It's messy and needs some
# refactoring and additional features.  It should be possible to keep this
# API and integrate callbacks so they get invoked from the mainloop, rather
# than directly on signal emission.

import weakref, types

class WeakRefMethod:
    def __init__(self, method, destroy_callback = None):
        # FIXME: need to handle weakref finalize callback
        self.instance = weakref.ref(method.im_self, destroy_callback)
        self.func_name = method.im_func.func_name

    def get(self):
        if self.instance() == None:
            return False
        return getattr(self.instance(), self.func_name)

    def __call__(self, *args):
        if self.instance() == None:
            print "Method died, returning False"
            return False
        meth = self.get()
        if not meth:
            return False
        return self.get()(*args)


class Signal:
    def __init__(self):
        self.callbacks = []
        self._items = {}

    def __del__(self):
        pass
#        print "Signal deleting", self.callbacks

    def __getitem__(self, name):
        return self._items[name]

    def __contains__(self, name):
        return name in self._items

    def __setitem__(self, name, value):
        self._items[name] = value

    def connect(self, callback, data = None, once = False, pos = -1):
        if (callback, data, once) not in self.callbacks:
            if pos == -1:
                pos = len(self.callbacks)
            self.callbacks.insert(pos,  (self._ref(callback), self._ref(data), once) )
        return self

    def connect_first(self, callback, data = None, once = False):
        self.connect(callback, data, once, 0)

    def disconnect(self, callback, data = None, once = False):
        # FIXME: won't match if stored data has weakrefs
        found = False
        for (cb_callback, cb_data, cb_once) in self.callbacks:
            if self._unref(cb_callback) == callback and self._unref(cb_data) == data:
                self.callbacks.remove( (cb_callback, cb_data, cb_once) )
                found = True
        if not found:
            print "*** DISCONNECT FAILED", callback, data, once

    def disconnect_all(self):
        self.callbacks = []

#    def disconnect_by_object(self, object):
#        # BROKEN
#        for (callback, data, once) in self.callbacks[:]:
#            if hasattr(callback, "im_self") and callback.im_self == object:
#                self.callbacks.remove( (callback, data, once) )
#                print "Remove callback because im_self == object", callback, data, once
#            if data == object or type(data) in (types.ListType, types.TupleType) and object in data:
#                self.callbacks.remove( (callback, data, once) )
#                print "Remove callback because object in data"

    def emit(self, *data, **kwargs):
        res = False
        if "clean" in kwargs and kwargs["clean"]:
            data = filter(lambda x: x != None, data)
        if len(self.callbacks) > 40:
            print "Signal callbacks exceeds 40; something's wrong!", self, data
            print self.callbacks[0][0].get()
            raise Exception
        for (callback, cb_data, once) in self.callbacks[:]:
            if not callable(callback):
                self.callbacks.remove( (callback, cb_data, once) )
                continue

            args = []
            if len(data): args.extend(data)
            cb_data = self._unref(cb_data)
            if cb_data != None: 
                if type(cb_data) in (types.ListType, types.TupleType):
                    args.extend(cb_data)
                else:
                    args.append(cb_data)

            if callback(*tuple(args)):
                res = True
            if once:
                self.disconnect(self._unref(callback), self._unref(cb_data), once)
        return res

    def _weakref_destroyed(self, ref):
        # TODO: implement me
        #print "### Weakref destroyed", ref
        pass

    def _ref(self, data):
        if callable(data) and hasattr(data, "im_self"):
            # Make weakref for methods
            return WeakRefMethod(data, self._weakref_destroyed)
        elif type(data) == types.InstanceType:
            return weakref.ref(data)
        elif type(data) in (types.ListType, types.TupleType):
            refed_data = []
            for item in data:
                refed_data.append(self._ref(item))
            if type(data) == types.TupleType:
                refed_data = tuple(refed_data)
            return refed_data

        return data

    def _unref(self, data):
        if isinstance(data, WeakRefMethod):
            return data.get()
        elif type(data) == weakref.ReferenceType:
            return data()
        elif type(data) in (types.ListType, types.TupleType):
            unrefed_data = []
            for item in data:
                unrefed_data.append(self._unref(item))
            if type(data) == types.TupleType:
                unrefed_data = tuple(unrefed_data)
                return unrefed_data

        return data

    def count(self):
        return len(self.callbacks)

############################################################################

