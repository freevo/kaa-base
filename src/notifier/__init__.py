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
import wrapper
from wrapper import Timer, OneShotTimer, Socket, Dispatcher, Shutdown
from wrapper import IO_READ, IO_WRITE, IO_EXCEPT
from posixsignals import *
from posixsignals import register as signal
from signals import Signal, WeakRefMethod
from popen import Process
from popen import killall as kill_processes
from thread import Thread, call_from_main
from callback import Callback, Function, CallbackObject

# get logging object
log = logging.getLogger('notifier')

# variable to check if the notifier is running
running = False


def select_notifier(type):
    """
    Select a notifier module. This only needs to be called when pyNotifier
    is used and not the notifier should be something else than the generic
    one. The variables for the different notifier are not available in this
    wrapper.
    """
    wrapper.select_notifier(type)

    global IO_READ
    global IO_WRITE
    global IO_EXCEPT

    IO_READ   = notifier.IO_READ
    IO_WRITE  = notifier.IO_WRITE
    IO_EXCEPT = notifier.IO_EXCEPT


def shutdown():
    """
    Shutdown notifier and kill all background processes.
    """
    if running:
        # notifier loop still running, send system exit
        log.info('Stop notifier loop')
        sys.exit(0)
    kill_processes()
    while wrapper.shutdown_callbacks:
        # call all shutdown functions
        wrapper.shutdown_callbacks.pop()()


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


# **** functions while freevo is ported to kaa.notifier ****
# WARNING: the following functions will be deleted in the future

def addShutdown(function):
    Shutdown(function).register()

def addTimer(interval, function, *args, **kwargs):
    t = Timer(function, *args, **kwargs)
    t.start(interval)
    return t.id

def timer(interval, function, *args, **kwargs):
    t = Timer(function, *args, **kwargs)
    t.remove = t.stop
    t.start(interval)
    return t

try:
    import notifier
except ImportError:
    import nf_generic as notifier

addSocket = notifier.addSocket
addDispatcher = notifier.addDispatcher
removeTimer = notifier.removeTimer
removeSocket = notifier.removeSocket
removeDispatcher = notifier.removeDispatcher
