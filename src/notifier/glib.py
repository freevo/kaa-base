# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# glib.py - Glib (gobject mainloop) thread wrapper
# -----------------------------------------------------------------------------
# $Id$
#
# This module makes it possible to run the glib mainloop in an extra thread
# and provides a hook to run callbacks in the glib thread. This module also
# supports using the glib mainloop as main mainloop. In that case, no threads
# are used.
#
# If you use this module to interact with a threaded glib mainloop, remember
# that callbacks from glib are also called from the glib thread.
#
# -----------------------------------------------------------------------------
# kaa.notifier - Mainloop and callbacks
# Copyright (C) 2008 Dirk Meyer, Jason Tackaberry, et al.
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

__all__ = [ 'GOBJECT', 'gobject_set_threaded' ]

# python imports
import threading

try:
    # try to import gobject
    import gobject
except ImportError:
    gobject = None

# get notifier thread module
import thread as thread_support

# object for kaa.threaded decorator
GOBJECT = object()

class Wrapper(object):
    """
    Glib wrapper with JobServer interface.
    """
    def __init__(self):
        # register this class as thread.JobServer
        thread_support._threads[GOBJECT] = self
        self.stopped = False
        self.thread = False
        self.init = False

    def set_threaded(self):
        """
        Start the glib mainloop in a thread.
        """
        if self.init:
            raise RuntimeError()
        if self.thread:
            return
        self.thread = True
        if gobject is not None:
            self._finished_event = threading.Event()
            gobject.threads_init()
            self.loop()

    @thread_support.threaded()
    def loop(self):
        """
        Glib thread.
        """
        loop = gobject.main_context_default()
        while not self.stopped:
            loop.iteration()
        print 'thread done'
        self._finished_event.set()

    def add(self, callback):
        """
        Add a callback.
        """
        self.init = True
        if not self.thread:
            return callback._execute()
        gobject.timeout_add(0, self._execute, callback)

    def _execute(self, callback):
        """
        Execute callback.
        """
        if callback is not None:
            callback._execute()
        return False

    def stop(self):
        """
        Stop the glib thread.
        """
        if self.stopped:
            return
        self.stopped = True
        if self.thread:
            self.add(None)

    def join(self):
        """
        Wait until the thread is done.
        """
        if self.thread:
            self._finished_event.wait()

# create object and expose set_threaded
gobject_set_threaded = Wrapper().set_threaded
