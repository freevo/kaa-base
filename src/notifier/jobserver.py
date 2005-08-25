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

__all__ = [ 'ThreadCallback' ]


# python imports
import threading
import logging
import sys

# kaa notifier imports
from callback import Signal, Callback
from thread import MainThreadCallback

# internal list of named threads
_jobserver = {}

# get logging object
log = logging.getLogger('notifier')

class ThreadCallback(Callback):
    def __init__(self, callback, *args, **kwargs):
        super(ThreadCallback, self).__init__(callback, *args, **kwargs)
        self.signals = { 'exception': Signal(),
                         'completed': Signal() }
        self._server = None

    def active(self):
        return self._server != None
    
    def register(self, name, priority=0):
        self.priority = priority
        if not _jobserver.has_key(name):
            _jobserver[name] = _JobServer(name)
        self._server = _jobserver[name]
        self._server.add(self)

    def unregister(self):
        if self.active():
            self._server.remove(self)
            self._server = None


class _JobServer(threading.Thread):

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
        self.condition.acquire()
        self.stopped = True
        self.condition.notify()
        self.condition.release()

    def add(self, job):
        self.condition.acquire()
        self.jobs.append(job)
        self.jobs.sort(lambda x,y: -cmp(x.priority, y.priority))
        self.condition.notify()
        self.condition.release()

    def remove(self, job):
        if job in self.jobs:
            self.condition.acquire()
            self.jobs.remove(job)
            self.condition.release()
            
    def run(self):
        while not self.stopped:
            self.condition.acquire()
            while not self.jobs and not self.stopped:
                self.condition.wait()
            if self.stopped:
                self.condition.release()
                continue
            job = self.jobs[0]
            self.jobs = self.jobs[1:]
            self.condition.release()
            try:
                job._server = None
                ret = job()
            except:
                if job.signals['exception'].count > 0:
                    MainThreadCallback(job.signals['exception'].emit, sys.exc_info()[1])()
            else:
                if job.signals['completed'].count > 0:
                    MainThreadCallback(job.signals['completed'].emit, ret)()
        log.debug('stop jobserver %s' % self.name)



# global killall function
def killall():
    """
    Kill all running job server. This function will be called when the
    notifier main loop stops.
    """
    for j in _jobserver.values():
        j.stop()
        j.join()
