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

__all__ = [ 'MainThreadCallback', 'Thread', 'is_mainthread' ]

# python imports
import os
import threading
import logging

# notifier imports
from callback import Callback, notifier

# get logging object
log = logging.getLogger('notifier')


class MainThreadCallback(Callback):
    def __init__(self, callback, *args, **kwargs):
        super(MainThreadCallback, self).__init__(callback, *args, **kwargs)
        self.lock = threading.Lock()
        self._sync_return = None
        self.set_async()

    def set_async(self, async = True):
        self._async = async

    def __call__(self, *args, **kwargs):
        if threading.currentThread() != _thread_notifier_mainthread:
            self.lock.acquire(False)

            _thread_notifier_lock.acquire()
            _thread_notifier_queue.append((self, args, kwargs))
            if len(_thread_notifier_queue) == 1:
                os.write(_thread_notifier_pipe[1], "1")
            _thread_notifier_lock.release()

            if not self._async:
                self.lock.acquire()

            return self._sync_return
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
        self.result_cb = None
        self.except_cb = None
        

    def start(self, callback=None, exception_callback = None):
        """
        Start the thread.
        """
        # remember callback
        if callback:
            self.result_cb = MainThreadCallback(callback)
        if exception_callback:
            self.except_cb = MainThreadCallback(exception_callback)
        # start the thread
        threading.Thread.start(self)


    def run(self):
        """
        Call the function and store the result
        """
        try:
            # run thread function
            result = self.function(*self.args, **self.kargs)
            if self.result_cb:
                # call callback from main loop
                self.result_cb(result)
        except Exception, e:
            log.exception('Thread crashed:')
            if self.except_cb:
                # call callback from main loop
                self.except_cb(e)
        # remove ourself from main
        MainThreadCallback(self.join)


def is_mainthread():
    """
    Return True if the caller is in the main thread right now.
    """
    return threading.currentThread() == _thread_notifier_mainthread



# For MainThread* callbacks
_thread_notifier_pipe = os.pipe()
_thread_notifier_queue = []
_thread_notifier_lock = threading.Lock()
_thread_notifier_mainthread = threading.currentThread()


def _thread_notifier_run_queue(fd):
    global _thread_notifier_queue
    _thread_notifier_lock.acquire()
    os.read(_thread_notifier_pipe[0], 1)
    while _thread_notifier_queue:
        callback, args, kwargs = _thread_notifier_queue[0]
        _thread_notifier_queue = _thread_notifier_queue[1:]
        callback(*args, **kwargs)
        callback.lock.acquire(False)
        callback.lock.release()
    _thread_notifier_lock.release()

notifier.addSocket(_thread_notifier_pipe[0], _thread_notifier_run_queue)
