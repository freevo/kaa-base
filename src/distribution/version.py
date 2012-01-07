# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# version.py - version handling for kaa modules
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# Copyright 2005-2012 Dirk Meyer, Jason Tackaberry
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

# python imports
import math

class Version(object):
    """
    Version information for kaa modules.
    """
    def __init__(self, version):
        """
        Set internal version as string.
        """
        self.version = str(version)

    def __str__(self):
        """
        Convert to string.
        """
        return self.version


    def __repr__(self):
        return str(self)


    def _cmp(self, b):
        """
        Numeric (if possible) or lexical comparison of each verison component.
        """
        parts = max(self.version.count('.'), b.count('.'))
        a = self.version.split('.') + ['0'] * (parts - self.version.count('.'))
        b = b.split('.') + ['0'] * (parts - b.count('.'))
        for ap, bp in zip(a, b):
            if ap.isdigit() and bp.isdigit():
                ap, bp = int(ap), int(bp)
            if ap < bp:
                return -1
            elif ap > bp:
                return 1
        return 0


    def __eq__(self, obj):
        # Don't just do a string compare, because we consider 0.99.0 == 0.99
        return self._cmp(obj) == 0


    # Python 2.
    def __cmp__(self, obj):
        return self._cmp(obj)


    # Python 3
    def __lt__(self, obj):
        return self._cmp(obj) == -1

    def __le__(self, obj):
        return self._cmp(obj) in (-1, 0)

    def __gt__(self, obj):
        return self._cmp(obj) == 1

    def __ge__(self, obj):
        return self._cmp(obj) in (1, 0)
