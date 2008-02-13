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

__all__ = [ 'NamedThreadCallback' ]


# python imports
import threading
import logging
import sys

# kaa notifier imports
from callback import Signal, Callback
import thread

# internal list of named threads
_threads = {}

# get logging object
log = logging.getLogger('notifier.thread')


class NamedThreadCallback(Callback):
    """
    A callback to run a function in a thread. This class is used by
    execute_in_thread, but it is also possible to use this call directly.
    """
    def __init__(self, thread_information, func, *args, **kwargs):
        Callback.__init__(self, func, *args, **kwargs)
        self.priority = 0
        if isinstance(thread_information, (list, tuple)):
            thread_information, self.priority = thread_information
        self._thread = thread_information


    def _create_job(self, *args, **kwargs):
        cb = Callback._get_callback(self)
        job = thread.ThreadInProgress(cb, *args, **kwargs)
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
