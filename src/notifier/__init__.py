# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# __init__.py - Interface to kaa.notifier
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# kaa.notifier - Mainloop and callbacks
# Copyright (C) 2005, 2006 Dirk Meyer, Jason Tackaberry, et al.
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

# python imports
import sys
import logging
import os
import time
import signal
import threading
import atexit

# kaa.notifier imports
import nf_wrapper as notifier

init = notifier.init

from popen import *
from callback import *
from thread import *
from timer import *
from sockets import *
from event import *
from yieldfunc import *
from jobserver import ThreadCallback, execute_in_thread
from jobserver import killall as kill_jobserver
from async import Progress, InProgress

from decorators import execute_in_timer, execute_in_mainloop

# get logging object
log = logging.getLogger('notifier')

# variable to check if the notifier is running
running = False
# Set if currently in shutdown() (to prevent reentrancy)
shutting_down = False

def _step_signal_changed(signal, flag):
    if flag == Signal.SIGNAL_CONNECTED and signal.count() == 1:
        notifier.dispatcher_add(signals["step"].emit)
    elif flag == Signal.SIGNAL_DISCONNECTED and signal.count() == 0:
        notifier.dispatcher_remove(signals["step"].emit)


signals = {
    "shutdown": Signal(),
    "step": Signal(changed_cb = _step_signal_changed),
}


def shutdown():
    """
    Shutdown notifier and kill all background processes.
    """
    global shutting_down

    # Ensure shutdown() is called from main thread.
    if not is_mainthread():
        return MainThreadCallback(shutdown)()

    if running:
        # notifier loop still running, send system exit
        log.info('Stop notifier loop')
        raise SystemExit

    if shutting_down:
        return
    shutting_down = True

    stop_all_processes()
    signals["shutdown"].emit()
    signals["shutdown"].disconnect_all()
    signals["step"].disconnect_all()

    # Kill processes _after_ shutdown emits to give callbacks a chance to
    # close them properly.
    kill_all_processes()
    kill_jobserver()
    # Collect any zombies
    try:
        os.waitpid(-1, os.WNOHANG)
    except:
        pass


def loop():
    """
    Notifier main loop function. It will loop until an exception
    is raised or sys.exit is called.
    """
    global running
    running = True

    set_current_as_mainthread()
    try:
        notifier.loop()
    except (KeyboardInterrupt, SystemExit):
        try:
            # This looks stupid, I know that. The problem is that if we have
            # a KeyboardInterrupt, that flag is still valid somewhere inside
            # python. The next system call will fail because of that. Since we
            # don't want a join of threads or similar fail, we use a very short
            # sleep here. In most cases we won't sleep at all because this sleep
            # fails. But after that everything is back to normal.
            time.sleep(0.001)
        except:
            pass
    except Exception, e:
        log.exception('loop')
    running = False
    shutdown()


def step(*args, **kwargs):
    """
    Notifier step function with signal support.
    """
    if not is_mainthread():
        # If step is being called from a thread, wake up the mainthread
        # instead of allowing the thread into notifier.step.
        wakeup()
        # Sleep for epsilon to prevent busy loops.
        time.sleep(0.001)
        return

    try:
        notifier.step(*args, **kwargs)
    except (KeyboardInterrupt, SystemExit):
        raise SystemExit


def _shutdown_check(*args):
    # Helper function to shutdown kaa on system exit
    # The problem is that pytgtk just exits python and
    # does not simply return from the main loop and kaa
    # can't call the shutdown handler. This is not a perfect
    # solution, e.g. with the generic notifier you can do
    # stuff after kaa.main() which is not possible with gtk
    global running
    if running:
        # If the kaa mainthread (i.e. thread the mainloop is running in)
        # is not the program's main thread, then is_mainthread() will be False
        # and we don't need to set running=False since shutdown() will raise a
        # SystemExit and things will exit normally.
        if is_mainthread():
            running = False
        shutdown()

# # catch SIGTERM if possible for a clean shutdown
if threading.enumerate()[0] == threading.currentThread():
    signal.signal(signal.SIGTERM, _shutdown_check)
else:
    log.info('kaa imported from thread, disable SIGTERM handler')
    
# check to make sure we really call our shutdown function
atexit.register(_shutdown_check)
