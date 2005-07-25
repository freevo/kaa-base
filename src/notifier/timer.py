# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# timer.py - Timer classes for the notifier
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

__all__ = [ 'Timer', 'WeakTimer', 'OneShotTimer', 'WeakOneShotTimer' ]

from callback import NotifierCallback, WeakNotifierCallback, notifier
from thread import MainThreadCallback, is_mainthread

class Timer(NotifierCallback):

    def __init__(self, callback, *args, **kwargs):
        super(Timer, self).__init__(callback, *args, **kwargs)
        self.restart_when_active = True


    def start(self, interval):
        if not is_mainthread():
            return MainThreadCallback(self.start, interval)()
        if self.active():
            if not self.restart_when_active:
                return
            self.unregister()
        self._id = notifier.addTimer(interval, self)


    def stop(self):
        if not is_mainthread():
            return MainThreadCallback(self.stop, interval)()
        self.unregister()


    def unregister(self):
        if self.active():
            notifier.removeTimer(self._id)
            self._id = None



class OneShotTimer(Timer):

    def __call__(self, *args, **kwargs):
        self.unregister()
        super(OneShotTimer, self).__call__(*args, **kwargs)
        return False



class WeakTimer(WeakNotifierCallback, Timer):
    pass

class WeakOneShotTimer(WeakNotifierCallback, OneShotTimer):
    pass

