# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# jobserver.py - Callback for threads
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# kaa.notifier - Mainloop and callbacks
# Copyright (C) 2005, 2006 Dirk Meyer, Jason Tackaberry, et al.
#
# First Version: Dirk Meyer <dmeyer@tzi.de>
# Maintainer:    Dirk Meyer <dmeyer@tzi.de>
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

__all__ = [ 'execute_in_thread', 'NamedThreadCallback' ]


# python imports
import threading
import logging
import sys

# kaa notifier imports
from callback import Signal, Callback
from async import InProgress
from thread import MainThreadCallback
import thread

# internal list of named threads
_threads = {}

# get logging object
log = logging.getLogger('notifier.thread')


def execute_in_thread(name=None, priority=0):
    """
    The decorator makes sure the function is always called in the thread
    with the given name. The function will return an InProgress object.
    """
    def decorator(func):

        def newfunc(*args, **kwargs):
            if name:
                return NamedThreadCallback((name, priority), func, *args, **kwargs)()
            t = thread.Thread(func, *args, **kwargs)
            t.wait_on_exit(False)
            return t.start()

        try:
            newfunc.func_name = func.func_name
        except TypeError:
            pass
        return newfunc

    return decorator


class InProgressCallback(InProgress):
    def __init__(self, callback, *args, **kwargs):
        InProgress.__init__(self)
        self._callback = Callback(callback, *args, **kwargs)


    def _execute(self):
        """
        Execute the callback. This function SHOULD be called __call__ but
        InProgress.__call__ returns the result. This is deprecated but
        still used.
        """
        if self._callback is None:
            return None
        try:
            MainThreadCallback(self.finished, self._callback())()
        except Exception, e:
            e._exc_info = sys.exc_info()
            MainThreadCallback(self.exception, e)()
        self._callback = None


    def active(self):
        """
        Return True if the callback is still waiting to be proccessed.
        """
        return self._callback is not None


    def stop(self):
        """
        Remove the callback from the thread schedule if still active.
        """
        self._callback = None


class NamedThreadCallback(Callback):
    """
    A callback to run a function in a thread. This class is used by
    execute_in_thread, but it is also possible to use this call directly.
    The class inherits from InProgress and will call the connected functions
    on termination or exception.
    """
    def __init__(self, thread_information, func, *args, **kwargs):
        Callback.__init__(self, func, *args, **kwargs)
        self.priority = 0
        if isinstance(thread_information, (list, tuple)):
            thread_information, self.priority = thread_information
        self._thread = thread_information


    def _create_job(self, *args, **kwargs):
        cb = Callback._get_callback(self)
        job = InProgressCallback(cb, *args, **kwargs)
        job.priority = self.priority
        if not _threads.has_key(self._thread):
            _threads[self._thread] = _Thread(self._thread)
        server = _threads[self._thread]
        server.add(job)
        return job


    def _get_callback(self):
        return self._create_job


class _Thread(threading.Thread):
    """
    Thread processing NamedThreadCallback jobs.
    """
    def __init__(self, name):
        log.debug('start jobserver %s' % name)
        threading.Thread.__init__(self)
        self.setDaemon(True)
        self.condition = threading.Condition()
        self.stopped = False
        self.jobs = []
        self.name = name
        self.start()


    def stop(self):
        """
        Stop the thread.
        """
        self.condition.acquire()
        self.stopped = True
        self.condition.notify()
        self.condition.release()


    def add(self, job):
        """
        Add a NamedThreadCallback to the thread.
        """
        self.condition.acquire()
        self.jobs.append(job)
        self.jobs.sort(lambda x,y: -cmp(x.priority, y.priority))
        self.condition.notify()
        self.condition.release()


    def remove(self, job):
        """
        Remove a NamedThreadCallback from the schedule.
        """
        if job in self.jobs:
            self.condition.acquire()
            self.jobs.remove(job)
            self.condition.release()


    def run(self):
        """
        Thread main function.
        """
        while not self.stopped:
            # get a new job to process
            self.condition.acquire()
            while not self.jobs and not self.stopped:
                # nothing to do, wait
                self.condition.wait()
            if self.stopped:
                self.condition.release()
                continue
            job = self.jobs.pop(0)
            self.condition.release()
            job._execute()
        # server stopped
        log.debug('stop thread %s' % self.name)



# global killall function
def killall():
    """
    Kill all running job server. This function will be called when the
    notifier main loop stops.
    """
    for j in _threads.values():
        j.stop()
        j.join()
