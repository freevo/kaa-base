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
import traceback

try:
    # try to import pyNotifier and wrap everything in it
    import notifier
    # init pyNotifier with the generic notifier
    notifier.init(notifier.GENERIC)
    use_pynotifier = True
except ImportError:
    # use a copy of nf_generic since pyNotifier isn't installed
    import nf_generic as notifier
    use_pynotifier = False
    
# kaa.notifier imports
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


def init(type):
    """
    Init the notifier module. This only needs to be called when pyNotifier
    is used and not the notifier should be something else than the generic
    one.
    """
    if not use_pynotifier:
        raise AttributeError('pyNotifier not installed')
    if type == notifier.GENERIC:
        raise AttributeError('generic notifier already running')
    notifier.init(type)
    for var in globals():
        if var in _notifier_vars:
            globals()[var] = getattr(notifier, var)


_shutdown_cb = []

def addShutdown(function):
    """
    Add a function to be called on shutdown.
    """
    if not function in _shutdown_cb:
        _shutdown_cb.append(function)
    return function


def removeShutdown(self, function):
    """
    Remove a function from the list that will be called on shutdown.
    """
    while function in _shutdown_cb:
        _shutdown_cb.remove(function)

        
def shutdown():
    """
    Shutdown notifier and kill all background processes.
    """
    if running:
        # notifier loop still running, send system exit
        log.info('Stop notifier loop')
        sys.exit(0)
    kill_processes()
    while _shutdown_cb:
        # call all shutdown functions
        _shutdown_cb.pop()()
        
    
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


def addTimer(interval, function, *args, **kwargs):
    """
    The first argument specifies an interval in milliseconds, the
    second argument a function. Optional parameters specify parameters
    to the called function. This is function is called after interval
    seconds. If it returns true it's called again after interval
    seconds, otherwise it is removed from the scheduler.
    This function returns an unique identifer which can be used to remove this
    timer.
    """
    if args or kwargs:
        # create callback object to be passed to the notifier
        function = Callback(function, *args, **kwargs)
    return notifier.addTimer(interval, function)


def timer(interval, function, *args, **kwargs):
    """
    The first argument specifies an interval in milliseconds, the
    second argument a function. Optional parameters specify parameters
    to the called function. This is function is called after interval
    seconds. If it returns true it's called again after interval
    seconds, otherwise it is removed from the scheduler.
    This function returns a callback object with a remove function to remove
    the timer from the notifier.
    """
    t = CallbackObject(function, *args, **kwargs)
    t.register('Timer', interval)
    return t


# Import all notifier variables that are needed by the user of this
# module. Mark them in _notifier_vars to be overwritten later in init.
_notifier_vars = []
for var in dir(notifier):
    if (var == var.upper() or var.startswith('add') or \
        var.startswith('remove')) and not var in globals():
        _notifier_vars.append(var)
        exec('%s = notifier.%s' % (var, var))

