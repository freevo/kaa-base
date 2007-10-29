# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# nf_thread.py - Thread based notifier to include in other mainloops
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

__all__ = [ 'init' ]

# python imports
import threading
import logging

# kaa.notifier imports
import kaa.notifier
import nf_wrapper

# get logging object
log = logging.getLogger('notifier')

class ThreadLoop(threading.Thread):
    """
    Thread running the kaa.notifier mainloop.
    """
    def __init__(self, interleave, shutdown = None):
        super(ThreadLoop, self).__init__()
        self.interleave = interleave
        self.condition = threading.Semaphore(0)
        self.sleeping = False
        self.shutdown = kaa.notifier.shutdown
        if shutdown:
            self.shutdown = shutdown


    def handle(self):
        """
        Callback from the real mainloop.
        """
        try:
            try:
                nf_wrapper.step(sleep = False)
            except (KeyboardInterrupt, SystemExit):
                kaa.notifier.running = False
        finally:
            self.condition.release()


    def run(self):
        """
        Thread part running the blocking, simulating loop.
        """
        kaa.notifier.running = True
        try:
            while True:
                self.sleeping = True
                nf_wrapper.step(simulate = True)
                self.sleeping = False
                if not kaa.notifier.running:
                    break
                self.interleave(self.handle)
                self.condition.acquire()
                if not kaa.notifier.running:
                    break
        except (KeyboardInterrupt, SystemExit):
            pass
        except Exception, e:
            log.exception('loop')
        kaa.notifier.running = False
        self.interleave(self.shutdown)


class Wakeup(object):
    """
    Wrapper around a function to wakeup the sleeping notifier loop
    when timer or sockets are added.
    """
    def __init__(self, loop, func):
        self.loop = loop
        self.func = func

    def __call__(self, *args, **kwargs):
        ret = self.func(*args, **kwargs)
        if self.loop.sleeping:
            kaa.notifier.wakeup()
        return ret


def get_handler(module):
    """
    Use the thread based mainloop with twisted.
    """
    if module == 'twisted':
        # get reactor and return callback
        from twisted.internet import reactor
        return reactor.callFromThread, reactor.stop
    raise RuntimeError('no handler defined for thread mainloop')


def init( module, handler = None, shutdown = None, **options ):
    """
    Init the notifier.
    """
    if handler == None:
        handler, shutdown = get_handler(module)
    loop = ThreadLoop(handler, shutdown)
    nf_wrapper.init( 'generic', force_internal=True, **options )
    # set main thread and init thread pipe
    kaa.notifier.set_current_as_mainthread()
    # adding a timer or socket is not thread safe in general but
    # an additional wakeup we don't need does not hurt. And in
    # simulation mode the step function does not modify the
    # internal variables.
    nf_wrapper.timer_add = Wakeup(loop, nf_wrapper.timer_add)
    nf_wrapper.socket_add = Wakeup(loop, nf_wrapper.socket_add)
    loop.start()
