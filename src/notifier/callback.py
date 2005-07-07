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

__all__ = [ 'Callback', 'Function', 'CallbackObject' ]

try:
    # try to import pyNotifier
    import notifier
except ImportError:
    # use a copy of nf_generic
    import nf_generic as notifier

class Callback(object):
    """
    Wrapper for functions calls with arguments inside the notifier. The
    function passed to this objects get the parameter passed to this object
    and after that the args and kwargs defined in the init function.
    """
    def __init__(self, function, *args, **kwargs):
        self.function = function
        self.args = args
        self.kwargs = kwargs


    def __call__(self, *args):
        """
        Call the callback function.
        """
        return self.function(*(list(args) + list(self.args)), **self.kwargs)


class Function(Callback):
    """
    Wrapper for functions calls with arguments inside the notifier. The
    function passed to this objects get the only args and kwargs defined in
    the init function, parameter passed to the object on call are dropped.
    """

    def __call__(self, *args, **kwargs):
        """
        Call the callback function.
        """
        return self.function(*self.args, **self.kwargs)


class CallbackObject(Callback):
    """
    Object to wrap notifier function calls with a remove function to remove
    the timer / socket later. Do not create an object like this outside the
    kaa.notifier source.
    """

    def register(self, type, *args):
        """
        Register the callback. Do not use this function directly.
        """
        self.type = type
        self.id = getattr(notifier, 'add' + type)(*(list(args) + [self]))


    def remove(self):
        """
        Remove the callback from the notifier.
        """
        if not hasattr(self, 'id'):
            raise AttributeError('Callback not registered')
        getattr(notifier, 'remove' + self.type)(self.id)
