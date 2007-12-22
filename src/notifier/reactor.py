# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# reactor.py - Twisted integration code
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# kaa.notifier - Mainloop and callbacks
# Copyright (C) 2007 Dirk Meyer, Jason Tackaberry, et al.
#
# First Version: Dirk Meyer <dmeyer@tzi.de>
# Maintainer:    Dirk Meyer <dmeyer@tzi.de>
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

# get and install reactor
from twisted.internet import threadedselectreactor

import kaa.notifier
import kaa.notifier.thread

class KaaReactor(threadedselectreactor.ThreadedSelectReactor):
    """
    Twisted reactor for kaa.notifier.
    """
    def _kaa_callback(self, func):
        """
        Callback from the Twisted thread kaa should execute from
        the mainloop.
        """
        a = kaa.notifier.MainThreadCallback(func)
        a.set_async(False)
        return a()


    def _kaa_stop(self):
        """
        Callback when Twisted wants to stop.
        """
        if not kaa.notifier.is_mainthread():
            return kaa.notifier.MainThreadCallback(twisted_stop)()
        kaa.notifier.OneShotTimer(kaa.notifier.shutdown).start(0)
        kaa.notifier.signals['shutdown'].disconnect(self.stop)


    def connect(self):
        """
        Connect the reactor to kaa.notifier.
        """
        self.interleave(self._kaa_callback)
        self.addSystemEventTrigger('after', 'shutdown', self._kaa_stop)
        kaa.notifier.signals['shutdown'].connect(self.stop)


    def run(self, installSignalHandlers=1):
        """
        Run the reactor by starting the notifier mainloop.
        """
        self.startRunning(installSignalHandlers=installSignalHandlers)
        kaa.notifier.loop()


def install():
    """
    Configure the twisted mainloop to be run using the kaa reactor.
    """
    reactor = KaaReactor()
    from twisted.internet.main import installReactor
    installReactor(reactor)
    reactor.connect()
    return reactor
