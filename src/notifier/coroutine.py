# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# coroutine.py - coroutine decorator and helper functions
# -----------------------------------------------------------------------------
# $Id$
#
# This file contains a decorator usefull for functions that may need more
# time to execute and that needs more than one step to fullfill the task.
#
# A caller of a function decorated with 'coroutine' will either get the
# return value of the function call or an InProgress object in return. The
# first is similar to a normal function call, if an InProgress object is
# returned, this means that the function is still running. The object has a
# 'connect' function to connect a callback to get the results of the function
# call when it is done.
#
# A function decorated with 'coroutine' can't use 'return' to return the
# result of the function call. Instead it has to use yield to do this. Besides
# a normal return, the function can also return 'NotFinished' in the yield
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
# The 'coroutine' decorator has a parameter interval. This is the
# interval used to schedule when the function should continue after a yield.
# The default value is 0, the first iteration is always called without a timer.
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

__all__ = [ 'NotFinished', 'YieldCallback', 'coroutine' ]

# python imports
import sys

# kaa.notifier imports
from signals import Signal
from timer import Timer
from async import InProgress

# object to signal that the function whats to continue
NotFinished = object()


class YieldCallback(InProgress):
    """
    Callback class that can be used as a callback for a function that is
    async. Return this object using 'yield' and use get_result() later.
    You can also use result = yield YieldCallback object for Python 2.5.
    """
    def __init__(self, func=None):
        InProgress.__init__(self)
        if func is not None:
            if isinstance(func, Signal):
                func = func.connect_once
            # connect self as callback
            func(self)


    def __call__(self, *args, **kwargs):
        """
        Call the YieldCallback by the external function. This will resume
        the calling YieldFunction.
        """
        # try to get the results as the caller excepts them
        if args and kwargs:
            # no idea how to merge them
            return self.finished((args, kwargs))
        if kwargs and len(kwargs) == 1:
            # return the value
            return self.finished(kwargs.values()[0])
        if kwargs:
            # return as dict
            return self.finished(kwargs)
        if len(args) == 1:
            # return value
            return self.finished(args[0])
        if len(args) > 1:
            # return as list
            return self.finished(args)
        return self.finished(None)


# variable to detect if send is possible with a generator
_python25 = sys.version.split()[0] > '2.4'

def _process(func, async=None):
    """
    function to call next, step, or throw
    """
    if _python25 and async is not None:
        if async._exception:
            async._unhandled_exception = None
            return func.throw(*async._exception)
        return func.send(async._result)
    return func.next()


def _wrap_result(result):
    """
    Wrap the result in a finished InProgress object.
    """
    async = InProgress()
    async.finished(result)
    return async


def coroutine(interval = 0, synchronize = False):
    """
    Functions with this decorator uses yield to break and to return the
    results. Special yield values for break are NotFinished or
    InProgress objects. If synchronize is True the function will
    be protected against parallel calls, which can be used avoid
    multithreading pitfalls such as deadlocks or race conditions.
    If a decorated function is currently being executed, new
    invocations will be queued.

    A function decorated with this decorator will always return an
    InProgress object. It may already be finished. If it is not finished,
    it has stop() and set_interval() member functions. If stop() is called,
    the InProgress object will emit the finished signal.
    """
    def decorator(func):
        def newfunc(*args, **kwargs):
            result = func(*args, **kwargs)
            if not hasattr(result, 'next'):
                # Decorated function doesn't have a next attribute, which
                # means it isn't a generator.  We might simply wrap the result
                # in an InProgress and pass it back, but for example if the
                # coroutine is wrapping a @threaded decorated function which is
                # itself a generator, wrapping the result will silently not work
                # with any indication why.  It's better to raise an exception.
                raise ValueError('@coroutine decorated function is not a generator')

            function = result
            if synchronize and func._lock is not None and not func._lock.is_finished():
                # Function is currently called by someone else
                return YieldLock(func, function, interval)
            async = None
            while True:
                try:
                    result = _process(function, async)
                except StopIteration:
                    # no return with yield, but done, return None
                    return _wrap_result(None)
                if isinstance(result, InProgress):
                    if result.is_finished():
                        # InProgress return that is already finished, go on
                        async = result
                        continue
                elif result != NotFinished:
                    # everything went fine, return result
                    return _wrap_result(result)
                # we need a YieldFunction to finish this later
                # result is either NotFinished or InProgress
                progress = YieldFunction(function, interval, result)
                if synchronize:
                    func._lock = progress
                # return the YieldFunction (InProgress)
                return progress

        if synchronize:
            func._lock = None
        newfunc.func_name = func.func_name
        return newfunc

    return decorator


# -----------------------------------------------------------------------------
# Internal classes
# -----------------------------------------------------------------------------

class YieldFunction(InProgress):
    """
    InProgress class that runs a generator function. This is also the return value
    for coroutine if it takes some more time. progress can be either None
    (not started yet), NotFinished (iterate now) or InProgress (wait until
    InProgress is done).
    """
    def __init__(self, function, interval, progress=None):
        InProgress.__init__(self)
        self._yield_function = function
        self._timer = Timer(self._step)
        self._interval = interval
        self._async = None
        self._valid = True
        if progress is None:
            # No progress from coroutine, this means that the YieldFunction
            # was created from the outside and the creator must call this object
            self._valid = False
        elif progress == NotFinished:
            # coroutine was stopped NotFinished, start the step timer
            self._timer.start(interval)
        elif isinstance(progress, InProgress):
            # continue when InProgress is done
            self._async = progress
            progress.connect_both(self._continue, self._continue)
        else:
            raise RuntimeError('YieldFunction with bad progress %s' % progress)


    def __call__(self, *args, **kwargs):
        """
        Call the YieldFunction to start it if it was not created by
        coroutine.
        """
        if self._valid:
            raise RuntimeError('YieldFunction already running')
        self._valid = True
        # The generator was not started yet
        self._yield_function = self._yield_function(*args, **kwargs)
        self._timer.start(self._interval)


    def _continue(self, *args, **kwargs):
        """
        Restart timer to call _step() after interval seconds.
        """
        if self._timer:
            self._timer.start(self._interval)


    def _step(self):
        """
        Call next step of the coroutine.
        """
        try:
            while True:
                result = _process(self._yield_function, self._async)
                if isinstance(result, InProgress) and result.is_finished():
                    # the result is a finished InProgress object
                    self._async = result
                    continue
                if result == NotFinished:
                    # schedule next interation with the timer
                    return True
                # YieldFunction is done with result
                break
        except StopIteration:
            # YieldFunction is done without result
            result = None
        except Exception, e:
            # YieldFunction is done with exception
            self.stop()
            self.throw(*sys.exc_info())
            return False

        if isinstance(result, InProgress):
            # continue when InProgress is done
            self._async = result
            result.connect_both(self._continue, self._continue)
            return False

        # YieldFunction is done
        self.stop()
        self.finished(result)
        return False


    def set_interval(self, interval):
        """
        Set a new interval for the internal timer.
        """
        if not self._timer:
            pass
        if self._timer.active():
            # restart timer
            self._timer.start(interval)
        self._interval = interval


    def stop(self):
        """
        Stop the function, no callbacks called.
        """
        if self._timer and self._timer.active():
            self._timer.stop()
        # Remove the internal timer, the async result and the
        # generator function to remove bad circular references.
        self._timer = None
        self._yield_function = None
        self._async = None


class YieldLock(YieldFunction):
    """
    YieldFunction for handling locked coroutine functions.
    """
    def __init__(self, original_function, function, interval):
        YieldFunction.__init__(self, function, interval)
        self._func = original_function
        self._func._lock.connect_both(self._try_again, self._try_again)


    def _try_again(self, *args, **kwargs):
        """
        Try to start now.
        """
        if not self._func._lock.is_finished():
            # still locked by a new call, wait again
            self._func._lock.connect_both(self._try_again, self._try_again)
            return
        self._func._lock = self
        self._continue()
