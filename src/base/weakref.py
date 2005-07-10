# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# weakref.py - weak reference
# -----------------------------------------------------------------------------
# $Id$
#
# This file contains a wrapper for weakref that the weak reference can
# be used the same way the real object would be used.
#
# -----------------------------------------------------------------------------
# Freevo - A Home Theater PC framework
# Copyright (C) 2002-2004 Krister Lagerstrom, Dirk Meyer, et al.
#
# First Edition: Dirk Meyer <dmeyer@tzi.de>
# Maintainer:    Dirk Meyer <dmeyer@tzi.de>
#
# Please see the file freevo/Docs/CREDITS for a complete list of authors.
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

from _weakref import ref

class weakref(object):
    """
    This class represents a weak reference based on the python
    module weakref. The difference between weakref.ref and this class
    is that you can access the ref without calling it first.
    E.g.: foo = weak(bar) and bar has the attribute x. With a normal
    weakref.ref you need to call foo().x to get, this class makes it
    possible to just use foo.x.
    """
    def __init__(self, object):
        if object:
            if type(object) == weakref:
                self._ref = object._ref
            else:
                self._ref = ref(object)
        else:
            self._ref = None
            
    def __getattribute__(self, attr):
        if attr == "__class__" and self:
            return self._ref().__class__
        if attr == "_ref":
            return object.__getattribute__(self, attr)
        return getattr(self._ref(), attr)

    def __setattr__(self, attr, value):
        if attr == "_ref":
            object.__setattr__(self, attr, value)
        
        return setattr(self._ref(), attr, value)

    def __delattr__(self, attr):
        return delattr(self._ref(), attr)

    def __call__(self, *args, **kwargs):
        return self._ref()(*args, **kwargs)

    def __nonzero__(self):
        if self._ref and self._ref():
            return 1
        else:
            return 0

    def __cmp__(self, other):
        if type(other) == weakref:
            other = other._ref()
        return cmp(self._ref(), other)

    def __str__(self):
        if self._ref:
            return "<weakref proxy; %s>" % str(self._ref())
        else:
            return 'weak reference to None'
