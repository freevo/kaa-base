# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# yieldfunc.py - Yield decorator and helper functions
# -----------------------------------------------------------------------------
# $Id$
#
# This file contains a decorator usefull for functions that may need more
# time to execute and that needs more than one step to fullfill the task.
#
# A caller of a function decorated with 'yield_execution' will either get the
# return value of the function call or an InProgress object in return. The
# first is similar to a normal function call, if an InProgress object is
# returned, this means that the function is still running. The object has a
# 'connect' function to connect a callback to get the results of the function
# call when it is done.
#
# A function decorated with 'yield_execution' can't use 'return' to return the
# result of the function call. Instead it has to use yield to do this. Besides
# a normal return, the function can also return 'YieldContinue' in the yield
# statement. In that case, the function call continues at this point in the
# next notifier iteration. If the function itself has to wait for a result of
# a function call (either another yield function are something else working
# async), it can create a 'YieldCallback' object, add this as callback to the
# function it is calling and return this object using yield. In this case, the
# function will continue at this point when the other async call is finished.
# The function can use the 'get' function of the 'YieldCallback' to get the
# result of the async call. It is also possible to yield an InProgress object
# and call it later to get the results (or the exception).
#
# The 'yield_execution' decorator has a parameter interval. This is the
# interval used to schedule when the function should continue after a yield.
# The default value is 0, the first iteration is always called without a timer.
#
# -----------------------------------------------------------------------------
# kaa.notifier - Mainloop and callbacks
# Copyright (C) 2006-2007 Dirk Meyer, Jason Tackaberry, et al.
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

__all__ = [ 'YieldContinue', 'YieldCallback', 'yield_execution',
            'YieldFunction' ]

import sys
import logging

from callback import Signal
from timer import Timer
from async import InProgress

log = logging.getLogger('notifier.yield')

YieldContinue = object()

class YieldCallback(object):
    """
    Callback class that can be used as a callback for a function that is
    async. Return this object using 'yield' and use the memeber function
    'get' later to get the result.
    """
    def __init__(self, func=None):
        if func is not None:
            if isinstance(func, Signal):
                func = func.connect_once
            func(self)


    def __call__(self, *args, **kwargs):
        self._args = args
        self._kwargs = kwargs
        self._callback()
        self._callback = None
        return False


    def _connect(self, callback):
        self._callback = callback


    def get(self):
        """
        Return the result of the callback.
        """
        # try to get the results as the caller excepts them
        if self._args and self._kwargs:
            # no idea how to merge them
            return self._args, self._kwargs
        if self._kwargs and len(self._kwargs) == 1:
            # return the value
            return self._kwargs.values()[0]
        if self._kwargs:
            # return as dict
            return self._kwargs
        if len(self._args) == 1:
            # return value
            return self._args[0]
        if len(self._args) > 1:
            # return as list
            return self._args
        return None


def yield_execution(interval=0, lock=False):
    """
    Functions with this decorator uses yield to break and to return the
    results. Special yield values for break are YieldContinue or
    YieldCallback or InProgress objects. In lock is True the function will
    be locked against parallel calls. If locked the call will delayed.
    """
    def decorator(func):

        def newfunc(*args, **kwargs):
            function = func(*args, **kwargs).next
            if lock and func._lock is not None and not func._lock.is_finished:
                return YieldLock(func, function, interval)
            try:
                result = function()
            except StopIteration:
                # no return with yield, but done, return None
                return None
            if not (result == YieldContinue or \
                    isinstance(result, (YieldCallback, InProgress))):
                # everything went fine, return result
                return result
            # we need a step callback to finish this later
            progress = YieldFunction(function, interval, result)
            if lock:
                func._lock = progress
            return progress

        func._lock = None
        newfunc.func_name = func.func_name
        return newfunc

    return decorator


# -----------------------------------------------------------------------------
# Internal classes
# -----------------------------------------------------------------------------

class YieldInProgress(object):
    """
    Internal function to handle InProgress returns from yield.
    """
    def __init__(self, in_progress):
        self._in_progress = in_progress


    def _connect(self, callback):
        self._in_progress.connect(callback)
        self._in_progress.exception_handler.connect(callback)


    def __call__(self, *args, **kwargs):
        return self._in_progress()


class YieldFunction(InProgress):
    """
    InProgress class to continue function execution.
    """
    def __init__(self, function, interval, status=None):
        InProgress.__init__(self)
        self._yield__function = function
        self._timer = Timer(self._step)
        self._interval = interval
        if status == None:
            # call function later
            self._valid = False
            return
        self._valid = True
        if status == YieldContinue:
            return self._timer.start(interval)
        if isinstance(status, InProgress):
            status = YieldInProgress(status)
        status._connect(self._continue)


    def __call__(self, *args, **kwargs):
        if not self._valid:
            # setup call
            self._valid = True
            self._yield__function = self._yield__function(*args, **kwargs).next
            self._continue()
            return True
        return InProgress.__call__(self, *args, **kwargs)


    def _continue(self, *args, **kwargs):
        """
        Restart timer.
        """
        if self._timer:
            self._timer.start(self._interval)


    def _step(self):
        """
        Call next step of the yield function.
        """
        try:
            result = self._yield__function()
        except (SystemExit, KeyboardInterrupt):
            sys.exit(0)
        except StopIteration:
            result = None
        except Exception, e:
            log.exception('YieldFunction')
            self.exception(e)
            return False
        if result == YieldContinue:
            return True
        self._timer.stop()
        if isinstance(result, InProgress):
            result = YieldInProgress(result)
        if isinstance(result, (YieldCallback, YieldInProgress)):
            result._connect(self._continue)
            return False
        self._timer = None
        self.finished(result)
        return False


    def stop(self):
        """
        Stop the function, no callbacks called.
        """
        if self._timer and self._timer.active():
            self._timer.stop()
        self._timer = None
        self._yield__function = None


class YieldLock(YieldFunction):
    """
    YieldFunction for handling locked yield_execution functions.
    """
    def __init__(self, original_function, function, interval):
        YieldFunction.__init__(self, function, interval)
        self._func = original_function
        status = YieldInProgress(self._func._lock)
        status._connect(self._try_again)


    def _try_again(self, result):
        if not self._func._lock.is_finished:
            # still locked by a new call, wait again
            status = YieldInProgress(self._func._lock)
            status._connect(self._try_again)
            return
        self._func._lock = self
        self._continue()
