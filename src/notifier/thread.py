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
# If a thread needs to call a function from the main loop the helper function
# call_from_main can be used. It will schedule the function call in the main
# loop. It is not possible to get the return value of that call.
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

__all__ = [ 'Thread', 'call_from_main' ]

# python imports
import copy
import threading
import logging

# notifier imports
from callback import Timer

# get logging object
log = logging.getLogger('notifier')

# internal list of callbacks that needs to be called from the main loop
_callbacks = []

# lock for adding / removing callbacks from _callbacks
_lock = threading.Lock()

class Thread(threading.Thread):
    """
    Notifier aware wrapper for threads.
    """
    def __init__(self, function, *args, **kargs):
        threading.Thread.__init__(self)
        self.callbacks = [ None, None ]
        self.function  = function
        self.args      = args
        self.kargs     = kargs
        self.result    = None
        self.finished  = False
        self.exception = None


    def start(self, callback=None, exception_callback = None):
        """
        Start the thread.
        """
        # append object to list of threads in watcher
        _watcher.append(self)
        # register callback
        self.callbacks = [ callback, exception_callback ]
        # start the thread
        threading.Thread.start(self)


    def run(self):
        """
        Call the function and store the result
        """
        try:
            # run thread function
            self.result = self.function(*self.args, **self.kargs)
        except Exception, e:
            log.exception('Thread crashed:')
            self.exception = e
        # set finished flag
        self.finished = True


    def callback(self):
        """
        Run the callback.
        """
        if self.exception and self.callbacks[1]:
            self.callbacks[1](self.exception)
        elif not self.exception and self.callbacks[0]:
            self.callbacks[0](self.result)



def call_from_main(function, *args, **kwargs):
    """
    Call a function from the main loop. The function isn't called when this
    function is called, it is called when the watcher in the main loop is
    called by the notifier.
    """
    _lock.acquire()
    _callbacks.append((function, args, kwargs))
    _lock.release()


class Watcher(object):
    """
    Watcher for running threads.
    """
    def __init__(self):
        self.__threads = []
        self.__timer = Timer(self.check)


    def append(self, thread):
        """
        Append a thread to the watcher.
        """
        self.__threads.append(thread)
        if not self.__timer.active():
            self.__timer.start(10)


    def check(self):
        """
        Check for finished threads and callbacks that needs to be called from
        the main loop.
        """
        finished = []
        # check if callbacks needs to be called from the main loop
        if _callbacks:
            # acquire lock
            _lock.acquire()
            # copy callback list
            cb = copy.copy(_callbacks)
            while _callbacks:
                # delete callbacks
                _callbacks.pop()
            # release lock
            _lock.release()

            # call callback functions
            for function, args, kwargs in cb:
                function(*args, **kwargs)

        for thread in self.__threads:
            # check all threads
            if thread.finished:
                finished.append(thread)

        if not finished:
            # no finished thread, return
            return True

        # check all finished threads
        for thread in finished:
            # remove thread from list
            self.__threads.remove(thread)
            # call callback
            thread.callback()
            # join thread
            thread.join()

        if not self.__threads:
            # remove watcher from notifier
            return False
        return True


# the global watcher object
_watcher = Watcher()
