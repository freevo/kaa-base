# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# async.py - Async callback handling (InProgress)
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# kaa.notifier - Mainloop and callbacks
# Copyright (C) 2006 Dirk Meyer, Jason Tackaberry, et al.
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
    An InProgress class used to return from function calls
    that need more time to continue. It is possible to connect
    to an object of this class like Signals. The memeber 'exception_handler'
    is a second signal to get notification of an exception raised later.
    """
    def __init__(self):
        Signal.__init__(self)
        self.exception_handler = Signal()
        self.is_finished = False


    def finished(self, result):
        """
        This function should be called when the creating function is
        done and no longer in progress.
        """
        if isinstance(result, InProgress):
            # we are still not finished, register to this result
            result.connect(self.finished)
            result.exception_handler.connect(self.exception)
            return
        # store result
        self.is_finished = True
        self._result = result
        self._exception = None
        # emit signal
        self.emit(result)
        # cleanup
        self._callbacks = []
        self.exception_handler = None


    def exception(self, e):
        """
        This function should be called when the creating function is
        done because it raised an exception.
        """
        if self.exception_handler.count() == 0:
            trace = ''.join(traceback.format_exception(*e._exc_info))
            log.error('*** InProgress exception not handled ***\n%s', trace)
        # store result
        self.is_finished = True
        self._exception = e
        # emit signal
        self.exception_handler.emit(e)
        # cleanup
        self._callbacks = []
        self.exception_handler = None


    def __call__(self, *args, **kwargs):
        """
        You can call the InProgress object to get the results when finished.
        The function will either return the result or raise the exception
        provided to the exception function.
        """
        if not self.is_finished:
            raise RuntimeError('operation not finished')
        if self._exception:
            raise self._exception
        return self._result


    def get_result(self):
        """
        Get the results when finished.
        The function will either return the result or raise the exception
        provided to the exception function.
        """
        return self()

    
    def _connect(self, callback, args = (), kwargs = {}, once = False,
                 weak = False, pos = -1):
        """
        Internal connect function. Always set once to True because InProgress
        will be emited only once.
        """
        return Signal._connect(self, callback, args, kwargs, True, weak, pos)
