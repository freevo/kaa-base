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

__all__ = [ 'MainThreadCallback', 'Thread', 'is_mainthread', 'wakeup', 'set_current_as_mainthread' ]

# python imports
import sys
import os
import threading
import logging
import fcntl
import socket

# notifier imports
from callback import Callback, notifier, Signal

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

    def __call__(self, *args, **kwargs):
        if threading.currentThread() != _thread_notifier_mainthread:
            self.lock.acquire(False)

            _thread_notifier_lock.acquire()
            _thread_notifier_queue.insert(0, (self, args, kwargs))
            if len(_thread_notifier_queue) == 1:
                os.write(_thread_notifier_pipe[1], "1")
            _thread_notifier_lock.release()

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

        else:
            self._sync_return = super(MainThreadCallback, self).__call__(*args, **kwargs)
            return self._sync_return


class Thread(threading.Thread):
    """
    Notifier aware wrapper for threads.
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



# For MainThread* callbacks
_thread_notifier_pipe = os.pipe()
_thread_notifier_queue = []
_thread_notifier_lock = threading.Lock()
_thread_notifier_mainthread = threading.currentThread()

fcntl.fcntl(_thread_notifier_pipe[0] , fcntl.F_SETFL, os.O_NONBLOCK )
fcntl.fcntl(_thread_notifier_pipe[1] , fcntl.F_SETFL, os.O_NONBLOCK )


def wakeup():
    """
    Wake up main thread.
    """
    if len(_thread_notifier_queue) == 0:
        os.write(_thread_notifier_pipe[1], "1")
 
  
def set_current_as_mainthread():
    global _thread_notifier_mainthread
    _thread_notifier_mainthread = threading.currentThread()
 
    
def _thread_notifier_run_queue(fd):
    global _thread_notifier_queue
    try:
        os.read(_thread_notifier_pipe[0], 1000)
    except OSError:
        pass

    while _thread_notifier_queue:
        _thread_notifier_lock.acquire()
        callback, args, kwargs = _thread_notifier_queue.pop()
        _thread_notifier_lock.release()
        try:
            callback(*args, **kwargs)
        except ( KeyboardInterrupt, SystemExit ), e:
            callback.lock.acquire(False)
            callback.lock.release()
            raise SystemExit
        except Exception, callback._sync_exception:
            log.exception('mainthread callback')
        callback.lock.acquire(False)
        callback.lock.release()
    return True

notifier.socket_add(_thread_notifier_pipe[0], _thread_notifier_run_queue)
