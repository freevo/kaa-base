# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# __init__.py - Interface to kaa.notifier
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

# python imports
import sys
import logging
import os
import traceback
import time

# kaa.notifier imports
from popen import Process
from popen import kill_all_processes, stop_all_processes
from callback import Callback, WeakCallback, Signal, notifier
from thread import MainThreadCallback, Thread, is_mainthread, wakeup
from timer import Timer, WeakTimer, OneShotTimer, WeakOneShotTimer
from sockets import SocketDispatcher, WeakSocketDispatcher, Socket, \
     IO_READ, IO_WRITE, IO_EXCEPT
from event import Event, EventHandler, WeakEventHandler
from jobserver import ThreadCallback
from jobserver import killall as kill_jobserver
from kaa.base import utils

# get logging object
log = logging.getLogger('notifier')

# variable to check if the notifier is running
running = False
# Set if currently in shutdown() (to prevent reentrancy)
shutting_down = False

def _handle_stdin_keypress(fd):
    ch = utils.getch()
    signals["stdin_key_press_event"].emit(ch)
    return True


def _idle_signal_changed(signal, flag):
    if flag == Signal.SIGNAL_CONNECTED and signal.count() == 1:
        notifier.dispatcher_add(signal.emit)
    elif flag == Signal.SIGNAL_DISCONNECTED and signal.count() == 0:
        notifier.dispatcher_remove(signal.emit)


def _keypress_signal_changed(signal, flag):
    if flag == Signal.SIGNAL_CONNECTED and signal.count() == 1:
        utils.getch_enable()
        notifier.socket_add(sys.stdin, _handle_stdin_keypress)
    elif flag == Signal.SIGNAL_DISCONNECTED and signal.count() == 0:
        utils.getch_disable()
        notifier.socket_remove(sys.stdin)


signals = {
    "shutdown": Signal(),
    "idle": Signal(changed_cb = _idle_signal_changed),
    # Temporary until I find a better place.
    "stdin_key_press_event": Signal(changed_cb = _keypress_signal_changed),
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

    e = None
    try:
        notifier.loop()
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception, e:
        pass

    running = False
    shutdown()
    if e:
        # print last exception
        traceback.print_exc()


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
        pass
