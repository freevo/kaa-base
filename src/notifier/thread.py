# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# thread.py - Thread module for the notifier
# -----------------------------------------------------------------------------
# $Id$
#
# This module contains some wrapper classes for threading while running the
# notifier main loop. It should only be used when non blocking handling is not
# possible. The main loop itself is not thread save, the the function called in
# the thread should not touch any variables inside the application which are
# not protected by by a lock.
#
# You can create a Thread object with the function and it's
# arguments. After that you can call the start function to start the
# thread. This function has an optional parameter with a callback
# which will be called from the main loop once the thread is
# finished. The result of the thread function is the parameter for the
# callback.
#
# In most cases this module is not needed, please add a good reason why you
# wrap a function in a thread.
#
# -----------------------------------------------------------------------------
# kaa.notifier - Mainloop and callbacks
# Copyright (C) 2005, 2006 Dirk Meyer, Jason Tackaberry, et al.
#
# First Version: Dirk Meyer <dmeyer@tzi.de>
# Maintainer:    Dirk Meyer <dmeyer@tzi.de>
#                Jason Tackaberry <tack@sault.org>
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

__all__ = [ 'MainThreadCallback', 'Thread', 'is_mainthread', 'wakeup',
            'set_current_as_mainthread' ]

# python imports
import sys
import os
import threading
import logging
import fcntl
import socket
import errno

# notifier imports
import nf_wrapper as notifier
from callback import Callback, Signal
from async import InProgress

# get logging object
log = logging.getLogger('notifier')

class MainThreadCallback(Callback):
    def __init__(self, callback, *args, **kwargs):
        super(MainThreadCallback, self).__init__(callback, *args, **kwargs)
        self.lock = threading.Lock()
        self._sync_return = None
        self._sync_exception = None
        self.set_async()

    def set_async(self, async = True):
        self._async = async

    def _set_result(self, result):
        self._sync_return = result
        if isinstance(self._sync_return, InProgress):
            if not self._sync_return.is_finished:
                self._sync_return.connect(self._set_result)
                self._sync_return.exception_handler.connect(self._set_exception)
                return
            self._sync_return = self._sync_return()
        self._wakeup()

    def _set_exception(self, e):
        self._sync_exception = e
        self._wakeup()

    def _wakeup(self):
        self.lock.acquire(False)
        self.lock.release()

    def __call__(self, *args, **kwargs):
        if threading.currentThread() == _thread_notifier_mainthread:
            return super(MainThreadCallback, self).__call__(*args, **kwargs)

        self.lock.acquire(False)

        _thread_notifier_lock.acquire()
        _thread_notifier_queue.insert(0, (self, args, kwargs))
        if len(_thread_notifier_queue) == 1:
            if not _thread_notifier_pipe:
                _create_thread_notifier_pipe()
            os.write(_thread_notifier_pipe[1], "1")
        _thread_notifier_lock.release()

        # FIXME: what happens if we switch threads here and execute
        # the callback? In that case we may block because we already
        # have the result. Should we use a Condition here?

        if not self._async:
            # Synchronous execution: wait for main call us and collect
            # the return value.
            self.lock.acquire()
            if self._sync_exception:
                raise self._sync_exception

            return self._sync_return

        # Asynchronous: explicitly return None here.  We could return
        # self._sync_return and there's a chance it'd be valid even
        # in the async case, but that's non-deterministic and dangerous
        # to rely on.
        return None


class Thread(threading.Thread):
    """
    Notifier aware wrapper for threads. When a thread is started, it is
    impossible to fork the current process into a second one without exec both
    using the notifier main loop because of the shared _thread_notifier_pipe.
    """
    def __init__(self, function, *args, **kargs):
        threading.Thread.__init__(self)
        self.function  = function
        self.args      = args
        self.kargs     = kargs

        self.signals = {
            "completed": Signal(),
            "exception": Signal()
        }

    def _emit_and_join(self, signal, arg):
        """
        Run callback signals and join dead thread.
        """
        self.signals[signal].emit(arg)
        if self != threading.currentThread():
            # Only join if we're not the current thread (i.e. mainthread).
            self.join()


    def run(self):
        """
        Call the function and store the result
        """
        try:
            # run thread function
            result = self.function(*self.args, **self.kargs)
            MainThreadCallback(self._emit_and_join, "completed", result)()
        except:
            log.exception('Thread raised exception:')
            MainThreadCallback(self._emit_and_join, "exception", sys.exc_info()[1])()


def is_mainthread():
    """
    Return True if the caller is in the main thread right now.
    """
    # If threading module is None, assume main thread.  (Silences pointless
    # exceptions on shutdown.)
    return (not threading) or threading.currentThread() == _thread_notifier_mainthread



_thread_notifier_mainthread = threading.currentThread()
_thread_notifier_lock = threading.Lock()
_thread_notifier_queue = []

# For MainThread* callbacks. The pipe will be created when it is used the first
# time. This solves a nasty bug when you fork() into a second notifier based
# process without exec. If you have this pipe, communication will go wrong.
_thread_notifier_pipe = None

def _create_thread_notifier_pipe():
    global _thread_notifier_pipe
    log.info('create thread notifier pipe')
    _thread_notifier_pipe = os.pipe()

    fcntl.fcntl(_thread_notifier_pipe[0], fcntl.F_SETFL, os.O_NONBLOCK)
    fcntl.fcntl(_thread_notifier_pipe[1], fcntl.F_SETFL, os.O_NONBLOCK)

    notifier.socket_add(_thread_notifier_pipe[0], _thread_notifier_run_queue)

def wakeup():
    """
    Wake up main thread.
    """
    if not _thread_notifier_pipe:
        _create_thread_notifier_pipe()
    if len(_thread_notifier_queue) == 0:
        os.write(_thread_notifier_pipe[1], "1")


def set_current_as_mainthread():
    global _thread_notifier_mainthread
    _thread_notifier_mainthread = threading.currentThread()


def _thread_notifier_run_queue(fd):
    global _thread_notifier_queue
    try:
        os.read(_thread_notifier_pipe[0], 1000)
    except socket.error, (err, msg):
        if err == errno.EAGAIN:
            # Resource temporarily unavailable -- we are trying to read
            # data on a socket when none is avilable.  This should not
            # happen under normal circumstances, so log an error.
            log.error("Thread notifier pipe woke but no data available.")
    except OSError:
        pass

    while _thread_notifier_queue:
        _thread_notifier_lock.acquire()
        callback, args, kwargs = _thread_notifier_queue.pop()
        _thread_notifier_lock.release()
        try:
            # call callback and set result
            callback._set_result(callback(*args, **kwargs))
        except ( KeyboardInterrupt, SystemExit ), e:
            # only wakeup to make it possible to stop the thread
            callback._wakeup()
            raise SystemExit
        except Exception, e:
            log.exception('mainthread callback')
            # set exception in callback
            callback._set_exception(e)
    return True
