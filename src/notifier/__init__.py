# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# __init__.py - Interface to kaa.notifier
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# kaa.notifier - Mainloop and callbacks
# Copyright (C) 2005-2008 Dirk Meyer, Jason Tackaberry, et al.
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

from popen import Process
from callback import Callback, WeakCallback
from signals import Signal, Signals
from thread import MainThreadCallback, ThreadCallback, is_mainthread
from timer import Timer, WeakTimer, OneShotTimer, WeakOneShotTimer, AtTimer, OneShotAtTimer
from sockets import IOMonitor, WeakIOMonitor, Socket, IO_READ, IO_WRITE
from event import Event, EventHandler, WeakEventHandler
from coroutine import YieldContinue, YieldCallback, YieldFunction, coroutine
from jobserver import NamedThreadCallback
from async import InProgress
from decorators import timed, threaded, MAINTHREAD, POLICY_ONCE, POLICY_MANY, POLICY_RESTART



# XXX: wrappers for deprecated (renamed) decorators.  Everything below
# this comment can be removed once support for deprecated names is
# removed.
import logging
log = logging.getLogger('notifier')

def execute_in_mainloop(async=False):
    log.warning('Decorator @kaa.execute_in_mainloop deprecated; use @kaa.threaded(kaa.MAINTHREAD)');
    return threaded(MAINTHREAD, async=async)

def execute_in_timer(timer, interval, type=''):
    log.warning('Decorator @kaa.execute_in_timer deprecated; use @kaa.timed');
    if not type:
        type = POLICY_MANY
    if type == 'override':
        type = POLICY_RESTART
    return timed(interval, timer, type)

def wrap(func, old_name, new_name):
    def decorator(*args, **kwargs):
        log.warning('Decorator @kaa.%s deprecated; use @kaa.%s' % (old_name, new_name))
        return func(*args, **kwargs)
    return decorator

execute_in_thread=wrap(threaded, 'execute_in_thread', 'threaded')
yield_execution=wrap(coroutine, 'yield_execution', 'coroutine')
SocketDispatcher=wrap(IOMonitor, 'SocketDispatcher', 'IOMonitor')
WeakSocketDispatcher=wrap(IOMonitor, 'WeakSocketDispatcher', 'WeakIOMonitor')
