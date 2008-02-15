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
# async with an InProgress object) and it can create a 'InProgressCallback'
# object and use this as callback.
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

__all__ = [ 'NotFinished', 'coroutine' ]

# python imports
import sys

# kaa.notifier imports
from signals import Signal
from timer import Timer
from async import InProgress

# object to signal that the function whats to continue
NotFinished = object()


# variable to detect if send is possible with a generator
_python25 = sys.hexversion >= 0x02050000

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
                return CoroutineInProgressLock(func, function, interval)
            async = None
            while True:
                try:
                    result = _process(function, async)
                except StopIteration:
                    # no return with yield, but done, return None
                    result = None
                except Exception, e:
                    # exception handling, return finished InProgress
                    ip = InProgress()
                    ip.throw(*sys.exc_info())
                    return ip
                if isinstance(result, InProgress):
                    if result.is_finished():
                        # InProgress return that is already finished, go on
                        async = result
                        continue
                elif result != NotFinished:
                    # everything went fine, return result in an InProgress
                    ip = InProgress()
                    ip.finish(result)
                    return ip
                # we need a CoroutineInProgress to finish this later
                # result is either NotFinished or InProgress
                progress = CoroutineInProgress(function, interval, result)
                if synchronize:
                    func._lock = progress
                # return the CoroutineInProgress
                return progress

        if synchronize:
            func._lock = None
        newfunc.func_name = func.func_name
        return newfunc

    return decorator


# -----------------------------------------------------------------------------
# Internal classes
# -----------------------------------------------------------------------------

class CoroutineInProgress(InProgress):
    """
    InProgress class that runs a generator function. This is also the return value
    for coroutine if it takes some more time. progress can be either NotFinished
    (iterate now) or InProgress (wait until InProgress is done).
    """
    def __init__(self, function, interval, progress=None):
        InProgress.__init__(self)
        self._coroutine = function
        self._timer = Timer(self._step)
        self._interval = interval
        self._async = None
        self._valid = True
        if progress == NotFinished:
            # coroutine was stopped NotFinished, start the step timer
            self._timer.start(interval)
        elif isinstance(progress, InProgress):
            # continue when InProgress is done
            self._async = progress
            progress.connect_both(self._continue, self._continue)
        else:
            raise AttributeError('invalid progress %s' % progress)


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
                result = _process(self._coroutine, self._async)
                if isinstance(result, InProgress):
                    self._async = result
                    if not result.is_finished():
                        # continue when InProgress is done
                        self._async = result
                        result.connect_both(self._continue, self._continue)
                        return False
                elif result == NotFinished:
                    # schedule next interation with the timer
                    return True
                else:
                    # coroutine is done
                    break
        except StopIteration:
            # coroutine is done without result
            result = None
        except Exception, e:
            # coroutine is done with exception
            self.stop()
            self.throw(*sys.exc_info())
            return False
        self.stop()
        self.finish(result)
        return False


    def set_interval(self, interval):
        """
        Set a new interval for the internal timer.
        """
        if self._timer and self._timer.active():
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
        self._coroutine = None
        self._async = None


class CoroutineInProgressLock(CoroutineInProgress):
    """
    CoroutineInProgress for handling locked coroutine functions.
    """
    def __init__(self, original_function, function, interval):
        CoroutineInProgress.__init__(self, function, interval)
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
