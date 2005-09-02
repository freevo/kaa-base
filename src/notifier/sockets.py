# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# sockets.py - Socket (fd) classes for the notifier
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

__all__ = [ 'WeakCallback', 'WeakSocketDispatcher',
            'IO_READ', 'IO_WRITE', 'IO_EXCEPT' ]

from callback import NotifierCallback, WeakNotifierCallback, notifier
from thread import MainThreadCallback, is_mainthread

IO_READ   = notifier.IO_READ
IO_WRITE  = notifier.IO_WRITE
IO_EXCEPT = notifier.IO_EXCEPT


class SocketDispatcher(NotifierCallback):

    def __init__(self, callback, *args, **kwargs):
        super(SocketDispatcher, self).__init__(callback, *args, **kwargs)
        self.set_ignore_caller_args()


    def register(self, fd, condition = IO_READ):
        if self.active():
            return
        if not is_mainthread():
            return MainThreadCallback(self.register, fd, condition)()
        notifier.addSocket(fd, self, condition)
        self._condition = condition
        self._id = fd


    def unregister(self):
        if not self.active():
            pass
        if not is_mainthread():
            return MainThreadCallback(self.unregister)()
        notifier.removeSocket(self._id, self._condition)
        super(SocketDispatcher, self).unregister()



class WeakSocketDispatcher(WeakNotifierCallback, SocketDispatcher):
    pass

