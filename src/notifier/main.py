# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# main.py - Main loop functions
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

# python imports
import sys
import logging
import os
import time
import signal
import threading
import atexit

import nf_wrapper as notifier
from signals import Signal
from timer import OneShotTimer
from popen import proclist as _proclist
from thread import is_mainthread, wakeup, set_as_mainthread, threaded, MAINTHREAD
from thread import killall as kill_jobserver

__all__ = [ 'run', 'stop', 'step', 'select_notifier', 'is_running', 'wakeup',
            'set_as_mainthread', 'is_shutting_down', 'loop' ]

# get logging object
log = logging.getLogger('notifier')

# pid of the process running the notifier loop.  This lets run() know
# if we've just forked and we want to run a new loop.
_running_pid = None
# Set if currently in shutdown() (to prevent reentrancy)
_shutting_down = False

def _step_signal_changed(signal, flag):
    if flag == Signal.SIGNAL_CONNECTED and signal.count() == 1:
        notifier.dispatcher_add(signals["step"].emit)
    elif flag == Signal.SIGNAL_DISCONNECTED and signal.count() == 0:
        notifier.dispatcher_remove(signals["step"].emit)

signals = {
    'exception': Signal(),
    'shutdown': Signal(),
    'step': Signal(changed_cb = _step_signal_changed),
}


def select_notifier(module, **options):
    """
    Initialize the specified notifier.
    """
    if module in ('thread', 'twisted'):
        import nf_thread
        return nf_thread.init(module, **options)
    return notifier.init( module, **options )


def loop(condition, timeout = None):
    """
    Executes the main loop until condition is met.  condition is either a
    callable, or value that is evaluated after each step of the main loop.
    """
    initial_mainloop = False
    if not is_running():
        # no mainloop is running, set this thread as mainloop and
        # set the internal running state.
        initial_mainloop = True
        set_as_mainthread()
        _set_running(True)

    if not callable(condition):
        condition = lambda: condition

    abort = []
    if timeout is not None:
        # timeout handling to stop the mainloop after the given timeout
        # even when the condition is still True.
        timeout = OneShotTimer(lambda: abort.append(True))
        timeout.start(timeout)

    try:
        while condition() and not abort:
            try:
                notifier.step()
            except Exception, e:
                if signals['exception'].emit(*sys.exc_info()) != False:
                    # Either there are no global exception handlers, or none of
                    # them explicitly returned False to abort mainloop 
                    # termination.  So abort the main loop.
                    raise sys.exc_info()
    finally:
        # make sure we set mainloop status even for Exceptions we did not
        # catch. E.g. in Python 2.5 SystemExit and KeyboardInterrupt do not
        # inherit from Exception.
        if timeout is not None:
            timeout.stop(timeout)
        if initial_mainloop:
            _set_running(False)


def run():
    """
    Notifier main loop function. It will loop until an exception
    is raised or sys.exit is called.
    """
    if is_running():
        raise RuntimeError('Mainthread is already running')

    try:
        # Nested try necessary because python 2.4 doesn't support
        # try/except/finally.
        try:
            loop(True)
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
    finally:
        stop()


# Ensure stop() is called from main thread.
@threaded(MAINTHREAD)
def stop():
    """
    Shutdown notifier and kill all background processes.
    """
    global _shutting_down

    if is_running():
        # notifier loop still running, send system exit
        log.info('Stop notifier loop')
        raise SystemExit

    if _shutting_down:
        return

    _shutting_down = True

    _proclist.stop_all()
    signals["shutdown"].emit()
    signals["shutdown"].disconnect_all()
    signals["step"].disconnect_all()

    # Kill processes _after_ shutdown emits to give callbacks a chance to
    # close them properly.
    _proclist.kill_all()
    while _proclist.check():
        # wait until all processes are stopped
        step()
    kill_jobserver()
    # Collect any zombies
    try:
        os.waitpid(-1, os.WNOHANG)
    except:
        pass


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


def is_running():
    """
    Return if the main loop is currently running.
    """
    return _running_pid == os.getpid()


def is_shutting_down():
    """
    Return if the mainloop is currently inside stop()
    """
    return _shutting_down


def _set_running(status):
    """
    Set mainloop running status.
    """
    global _running_pid
    if status:
        _running_pid = os.getpid()
    else:
        _running_pid = None


def _shutdown_check(*args):
    # Helper function to shutdown kaa on system exit
    # The problem is that pytgtk just exits python and
    # does not simply return from the main loop and kaa
    # can't call the shutdown handler. This is not a perfect
    # solution, e.g. with the generic notifier you can do
    # stuff after kaa.main.run() which is not possible with gtk
    if is_running():
        # If the kaa mainthread (i.e. thread the mainloop is running in)
        # is not the program's main thread, then is_mainthread() will be False
        # and we don't need to set running=False since shutdown() will raise a
        # SystemExit and things will exit normally.
        if is_mainthread():
            _set_running(False)
        stop()


# catch SIGTERM and SIGINT if possible for a clean shutdown
if threading.enumerate()[0] == threading.currentThread():
    def signal_handler(*args):
        sys.exit(0)
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
else:
    log.info('kaa imported from thread, disable SIGTERM handler')
    
# check to make sure we really call our shutdown function
atexit.register(_shutdown_check)
