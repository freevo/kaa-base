# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# jobserver.py - Callback for threads
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

__all__ = [ 'execute_in_thread', 'ThreadCallback' ]


# python imports
import threading
import logging
import sys

# kaa notifier imports
from callback import Signal, Callback
from async import InProgress
from thread import MainThreadCallback

# internal list of named threads
_threads = {}

# get logging object
log = logging.getLogger('notifier.thread')


def execute_in_thread(name, priority=0):
    """
    The decorator makes sure the function is always called in the thread
    with the given name. The function will return an InProgress object.
    """
    def decorator(func):

        def newfunc(*args, **kwargs):
            t = ThreadCallback(func, *args, **kwargs)
            t.register(name, priority)
            return t

        try:
            newfunc.func_name = func.func_name
        except TypeError:
            pass
        return newfunc

    return decorator


class ThreadCallback(InProgress):
    """
    A callback to run a function in a thread. This class is used by
    execute_in_thread, but it is also possible to use this call directly.
    The class inherits from InProgress and will call the connected functions
    on termination or exception.
    """
    def __init__(self, function, *args, **kwargs):
        super(ThreadCallback, self).__init__()
        self._callback = Callback(function, *args, **kwargs)
        self._server = None


    def active(self):
        """
        Return True if the callback is still waiting to be proccessed.
        """
        return self._server != None


    def register(self, name, priority=0):
        """
        Register callback to a thread with the given name.
        """
        if self._server:
            return
        self.priority = priority
        if not _threads.has_key(name):
            _threads[name] = _Thread(name)
        self._server = _threads[name]
        self._server.add(self)


    def stop(self):
        """
        Remove the callback from the thread schedule if still active.
        """
        if self.active():
            self._server.remove(self)
            self._server = None


class _Thread(threading.Thread):
    """
    Thread processing ThreadCallback jobs.
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
        Add a ThreadCallback to the thread.
        """
        self.condition.acquire()
        self.jobs.append(job)
        self.jobs.sort(lambda x,y: -cmp(x.priority, y.priority))
        self.condition.notify()
        self.condition.release()


    def remove(self, job):
        """
        Remove a ThreadCallback from the schedule.
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
            # process the job
            job._server = None
            try:
                MainThreadCallback(job.finished, job._callback())()
            except:
                MainThreadCallback(job.exception, sys.exc_info()[1])()
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
