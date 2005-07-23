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

# kaa.notifier imports
from signals import *
from signals import register as signal
from popen import Process
from popen import killall as kill_processes
from thread import Thread, call_from_main
from callback import Callback, WeakCallback, Timer, WeakTimer, OneShotTimer, \
                     WeakOneShotTimer, SocketDispatcher, WeakSocketDispatcher,\
                     Signal, IO_READ, IO_WRITE, IO_EXCEPT, notifier
from event import Event, EventHandler, WeakEventHandler
from kaa.base import utils

# get logging object
log = logging.getLogger('notifier')

# variable to check if the notifier is running
running = False

def _handle_stdin_keypress(fd):
    ch = utils.getch()
    signals["stdin_key_press_event"].emit(ch)
    return True


def _idle_signal_changed(signal, flag):
    if flag == Signal.SIGNAL_CONNECTED and signal.count() == 1:
        notifier.addDispatcher(signal.emit)
    elif flag == Signal.SIGNAL_DISCONNECTED and signal.count() == 0:
        notifier.removeDispatcher(signal.emit)


def _keypress_signal_changed(signal, flag):
    if flag == Signal.SIGNAL_CONNECTED and signal.count() == 1:
        utils.getch_enable()
        notifier.addSocket(sys.stdin, _handle_stdin_keypress)
    elif flag == Signal.SIGNAL_DISCONNECTED and signal.count() == 0:
        utils.getch_disable()
        notifier.removeSocket(sys.stdin)


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
    if running:
        # notifier loop still running, send system exit
        log.info('Stop notifier loop')
        raise SystemExit

    kill_processes()
    signals["shutdown"].emit()


def loop():
    """
    Notifier main loop function. It will loop until an exception
    is raised or sys.exit is called.
    """
    # Sets a default root level logger if none exists.
    logger = logging.getLogger()
    if len(logger.handlers) == 0:
        formatter = logging.Formatter('%(levelname)s %(module)s'+ \
                                      '(%(lineno)s): %(message)s')
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)

    global running
    running = True

    while 1:
        try:
            notifier.loop()
        except (KeyboardInterrupt, SystemExit):
            break
        except Exception, e:
            if has_signal():
                log.info('Call Signal Handler')
            else:
                running = False
                raise e
    running = False
    shutdown()


def step(*args, **kwargs):
    """
    Notifier step function with signal support.
    """
    try:
        notifier.step(*args, **kwargs)
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception, e:
        if has_signal():
            log.info('Call Signal Handler')
        else:
            raise e
