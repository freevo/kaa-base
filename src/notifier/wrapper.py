# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# wrapper.py - Wrapper for pynotifier / nf_generic
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

try:
    # try to import pyNotifier
    import notifier
    # init pyNotifier with the generic notifier
    notifier.init(notifier.GENERIC)
    use_pynotifier = True

except ImportError:
    # use a copy of nf_generic
    import nf_generic as notifier
    use_pynotifier = False

IO_READ   = notifier.IO_READ
IO_WRITE  = notifier.IO_WRITE
IO_EXCEPT = notifier.IO_EXCEPT

def select_notifier(type):
    """
    Select a new notifier.
    """
    if not use_pynotifier:
        raise AttributeError('pyNotifier not installed')
    if type == notifier.GENERIC:
        raise AttributeError('generic notifier already running')
    notifier.init(type)

    global IO_READ
    global IO_WRITE
    global IO_EXCEPT

    IO_READ   = notifier.IO_READ
    IO_WRITE  = notifier.IO_WRITE
    IO_EXCEPT = notifier.IO_EXCEPT


class Timer(object):
    def __init__(self, function, *args, **kwargs):
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.id = None

    def start(self, intervall):
        if self.id != None:
            self.stop()
        self.id = notifier.addTimer(intervall, self.expire)

    def stop(self):
        if self.id != None:
            notifier.removeTimer(self.id)
            self.id = None

    def active(self):
        return self.id != None

    def expire(self):
        return self.function(*self.args, **self.kwargs)


class OneShotTimer(Timer):
    def expire(self):
        notifier.removeTimer(self.id)
        self.id = None
        self.function(*self.args, **self.kwargs)
        return False


class Socket(object):
    def __init__(self, fd, function, *args, **kwargs):
        self.fd = fd
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.id = None

    def register(self, condition = None):
        if self.id != None:
            return
        if condition == None:
            self.id = notifier.addSocket(self.fd, self.callback)
        else:
            self.id = notifier.addSocket(self.fd, self.callback, condition)

    def unregister(self):
        if self.id == None:
            return
        notifier.removeSocket(self.id)
        self.id = None

    def active(self):
        return self.id != None

    def callback(self, fd):
        self.function(fd, *self.args, **self.kwargs)


class Dispatcher(object):
    def __init__(self, function, *args, **kwargs):
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.id = None

    def register(self):
        if self.id != None:
            return
        self.id = notifier.addDispatcher(self.callback)

    def unregister(self):
        if self.id == None:
            return
        notifier.removeDispatcher(self.id)
        self.id = None

    def active(self):
        return self.id != None

    def callback(self):
        self.function(*self.args, **self.kwargs)


shutdown_callbacks = []

class Shutdown(object):
    def __init__(self, function, *args, **kwargs):
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.id = None

    def register(self):
        if not self in shutdown_callbacks:
            shutdown_callbacks.append(self)

    def unregister(self):
        if self in shutdown_callbacks:
            shutdown_callbacks.remove(self)

    def active(self):
        return self in shutdown_callbacks

    def __call__(self):
        self.function(*self.args, **self.kwargs)

