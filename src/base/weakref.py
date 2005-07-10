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

class weakref:
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
            self.__dict__['ref'] = ref(object)
        else:
            self.__dict__['ref'] = None
            
    def __getattr__(self, attr):
        return getattr(self.__dict__['ref'](), attr)

    def __setattr__(self, attr, value):
        return setattr(self.__dict__['ref'](), attr, value)

    def __nonzero__(self):
        if self.__dict__['ref'] and self.__dict__['ref']():
            return 1
        else:
            return 0

    def __cmp__(self, other):
        if isinstance(other, weakref):
            other = other.__dict__['ref']()
        return cmp(self.__dict__['ref'](), other)

    def __str__(self):
        if self.__dict__['ref']:
            return str(self.__dict__['ref']())
        else:
            return 'weak reference to None'

    def delattr(self, attr):
        if hasattr(self.__dict__['ref'](), attr):
            ref = self.__dict__['ref']()
            exec('del ref.%s' % attr)
