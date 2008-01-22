# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# async.py - Async callback handling (InProgress)
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# kaa.notifier - Mainloop and callbacks
# Copyright (C) 2006-2008 Dirk Meyer, Jason Tackaberry, et al.
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

__all__ = [ 'InProgress' ]

# python imports
import logging
import traceback

# kaa.notifier imports
from callback import Signal

# get logging object
log = logging.getLogger('notifier.async')


class InProgress(Signal):
    """
    An InProgress class used to return from function calls that need more time
    to continue. It is possible to connect to an object of this class like
    Signals. The member 'exception' is a second signal to get
    notification of an exception raised later.
    """
    class Progress(Signal):
        """
        Generic progress status object for InProgress. This object can be
        connected to an InProgress object using set_status and the caller
        can monitor the progress.
        """
        def __init__(self):
            super(Progress, self).__init__()
            self.percentage = 0
            self.pos = 0
            self.max = 0


        def set(self, pos, max=None):
            """
            Set new status. The new status is pos of max.
            """
            if max is not None:
                self.max = max
            self.pos = pos
            if pos > self.max:
                self.max = pos
            if self.max:
                self.percentage = (self.pos * 100) / self.max
            else:
                self.percentage = 0
            self.emit()


        def update(self, diff):
            """
            Update position by the given difference.
            """
            self.set(self.pos + diff)


        def get_progressbar(self, width=70):
            """
            Return a small ASCII art progressbar.
            """
            n = 0
            if self.max:
                n = int((self.pos / float(self.max)) * (width-3))
            s = '|%%%ss|' % (width-2)
            return s % ("="*n + ">").ljust(width-2)


    def __init__(self):
        """
        Create an InProgress object.
        """
        Signal.__init__(self)
        self.exception = Signal()
        self._finished = False
        self.status = None


    def set_status(self, s):
        """
        Connect a status object to the InProgress object. The status object
        has to be updated by the creator of that object. The status should
        be a Signal so the monitoring function can connect to it to get
        notified on updates.
        """
        self.status = s


    def get_status(self):
        """
        Return status object if connected or return True if the function is
        still in progress or False if not.
        """
        if self.status is not None:
            return self.status
        return not self._finished


    def finished(self, result):
        """
        This function should be called when the creating function is
        done and no longer in progress.
        """
        if isinstance(result, InProgress):
            # we are still not finished, register to this result
            result.connect(self.finished)
            result.exception.connect(self.throw)
            return
        # store result
        self._finished = True
        self._result = result
        self._exception = None
        # emit signal
        self.emit_when_handled(result)
        # cleanup
        self._callbacks = []


    def throw(self, type, value, tb):
        """
        This function should be called when the creating function is
        done because it raised an exception.
        """
        if self.exception.count() == 0:
            # FIXME: we must still log the exception if we have an internal
            # handler but no external handler.  In this case count() > 0.
            # There is no handler, so dump the exception.
            trace = ''.join(traceback.format_exception(type, value, tb))
            log.error('*** Unhandled InProgress exception ***\n%s', trace)

        # store result
        self._finished = True
        self._exception = type, value, tb
        # emit signal
        self.exception.emit_when_handled(type, value, tb)
        # cleanup
        self._callbacks = []


    def __call__(self, *args, **kwargs):
        """
        You can call the InProgress object to get the results when finished.
        The function will either return the result or raise the exception
        provided to the exception function.
        """
        log.warning('Deprecated call to InProgress(); use get_result() instead')
        return self.get_result()
    

    def is_finished(self):
        """
        Return if the InProgress is finished.
        """
        return self._finished


    def get_result(self):
        """
        Get the results when finished.
        The function will either return the result or raise the exception
        provided to the exception function.
        """
        if not self._finished:
            raise RuntimeError('operation not finished')
        if self._exception:
            type, value, tb = self._exception
            # Special 3-argument form of raise; preserves traceback
            raise type, value, tb
        return self._result


    def _connect(self, callback, args = (), kwargs = {}, once = False,
                 weak = False, pos = -1):
        """
        Internal connect function. Always set once to True because InProgress
        will be emited only once.
        """
        return Signal._connect(self, callback, args, kwargs, True, weak, pos)


    def connect_both(self, finished, exception):
        """
        Connect a finished and an exception callback without extra arguments.
        """
        self.connect(finished)
        self.exception.connect(exception)
