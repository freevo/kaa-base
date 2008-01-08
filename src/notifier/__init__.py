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
from callback import Callback, WeakCallback, Signal, Signals
from thread import MainThreadCallback, Thread, is_mainthread, wakeup
from timer import Timer, WeakTimer, OneShotTimer, WeakOneShotTimer, AtTimer, OneShotAtTimer
from sockets import SocketDispatcher, WeakSocketDispatcher, Socket, IO_READ, IO_WRITE
from event import Event, EventHandler, WeakEventHandler
from yieldfunc import YieldContinue, YieldCallback, YieldFunction, yield_execution
from jobserver import ThreadCallback, execute_in_thread
from async import Progress, InProgress
from decorators import execute_in_timer, execute_in_mainloop

# Here's what will be imported into the kaa namespace.
__all__ = [
    'Process', 'Callback', 'WeakCallback', 'Signal', 'Signals', 'MainThreadCallback',
    'Thread', 'Timer', 'WeakTimer', 'OneShotTimer', 'WeakOneShotTimer', 'AtTimer',
    'OneShotAtTimer', 'SocketDispatcher', 'WeakSocketDispatcher', 'Socket',
    'IO_READ', 'IO_WRITE', 'Event', 'EventHandler', 'WeakEventHandler',
    'YieldContinue', 'YieldCallback', 'YieldFunction', 'ThreadCallback', 'InProgress',

    # decorator for sub modules
    # FIXME: while we are breaking the API right now, do we want to keep
    # these names and keep them in the global kaa scope?
    'execute_in_timer', 'execute_in_mainloop', 'yield_execution', 'execute_in_thread',

    # FIXME: I don't like the following functions in the global kaa namespace
    'is_mainthread', 'wakeup',
    
    # FIXME: this this needed somewhere? Maybe make it a subclass of InProgress
    'Progress',

    # XXX: DEPRECATED wrappers From this module
    'init', 'shutdown', 'step', 'running', 'signals', 'loop'
]

import main

# XXX: support for deprecated API.  Delete everything below when support is removed.

# get logging object
import logging
log = logging.getLogger('notifier')

def wrap(old_name, new_name, *args, **kwargs):
    def f(*args, **kwargs):
        log.warning('Deprecated call to notifier.%s(); use main.%s() instead' % (old_name, new_name))
        return getattr(main, new_name)(*args, **kwargs)
    return f

class RunningWrapper:
    def __nonzero__(self):
        log.warning('Deprecated access of notifier.running; use main.is_running() instead')
        return main.is_running()

init = wrap('init', 'select_notifier')
loop = wrap('loop', 'start')
shutdown = wrap('shutdown', 'stop')
step = wrap('step', 'step')
signals = main.signals
running = RunningWrapper()
