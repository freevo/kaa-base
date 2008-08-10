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
from kaa.utils import wraps
from signals import Signal
from timer import Timer
from async import InProgress, inprogress

# object to signal that the function whats to continue
NotFinished = object()

# Currently running (not stopped) CoroutineLockedInProgress objects.  See
# CoroutineLockedInProgress.__init__ for rational.
_active_coroutines = set()

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


def coroutine(interval = 0, synchronize = False, progress=False):
    """
    Functions with this decorator uses yield to break and to return the
    results. Special yield values for break are NotFinished or
    InProgress objects. If synchronize is True the function will
    be protected against parallel calls, which can be used avoid
    multithreading pitfalls such as deadlocks or race conditions.
    If a decorated function is currently being executed, new
    invocations will be queued. If progress is True, the first argument
    to the function is an InProgress.Progress object to return execution
    progress.

    A function decorated with this decorator will always return an
    InProgress object. It may already be finished. If it is not finished,
    it has stop() and set_interval() member functions. If stop() is called,
    the InProgress object will emit the finished signal.
    """
    if progress is True:
        progress = InProgress.Progress

    def decorator(func):
        @wraps(func)
        def newfunc(*args, **kwargs):
            def wrap(obj):
                if progress:
                    obj.progress = args[0]
                return obj
            if progress:
                args = [ progress(), ] + list(args)
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
                return wrap(CoroutineLockedInProgressLock(func, function, interval))
            async = None
            while True:
                try:
                    result = _process(function, async)
                except StopIteration:
                    # no return with yield, but done, return None
                    result = None
                except:
                    # exception handling, return finished InProgress
                    ip = InProgress()
                    ip.throw(*sys.exc_info())
                    return wrap(ip)

                if isinstance(result, InProgress):
                    if result.finished:
                        # coroutine yielded a finished InProgress, we can
                        # step back into the coroutine immediately.
                        async = result
                        continue
                elif result is not NotFinished:
                    # Coroutine yielded a value, so we're done and can return a
                    # finished InProgress.
                    return wrap(InProgress().finish(result))

                # we need a CoroutineLockedInProgress to finish this later
                # Here, result is either NotFinished or InProgress
                ip = CoroutineLockedInProgress(function, interval, result)
                if synchronize:
                    func._lock = ip
                # return the CoroutineLockedInProgress
                return wrap(ip)

        if synchronize:
            func._lock = None
        return newfunc

    return decorator


# -----------------------------------------------------------------------------
# Internal classes
# -----------------------------------------------------------------------------

class CoroutineLockedInProgress(InProgress):
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

        # This object (self) represents a coroutine that is in progress: that
        # is, at some point in the coroutine, it has yielded and expects
        # to be reentered at some point.  Even if there are no outside
        # references to this CoroutineLockedInProgress object, the coroutine must
        # resume.
        #
        # Here, an "outside reference" refers to a reference kept by the
        # caller of the API (that is, not refs kept by kaa internally).
        #
        # For other types of InProgress objects, when there are no outside
        # references to them, clearly nobody is interested in the result, so
        # they can be destroyed.  For CoroutineLockedInProgress, we mustn't rely
        # on outside references to keep the coroutine alive, so we keep refs
        # for active CoroutineLockedInProgress objects in a global set called
        # _active_coroutines.  We then then remove ourselves from this set when
        # stopped.
        #
        _active_coroutines.add(self)

        if progress is NotFinished:
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
                if result is NotFinished:
                    # Schedule next iteration with the timer
                    return True
                elif not isinstance(result, InProgress):
                    # Coroutine is done.
                    break

                # result is an InProgress
                self._async = result
                if not result.finished:
                    # Coroutine yielded an unfinished InProgress, so continue
                    # when it is finished.
                    result.connect_both(self._continue, self._continue)
                    # Return False to stop the step timer.  It will be
                    # restarted when this newly returned InProgress is
                    # finished.
                    return False

                # If we're here, then the coroutine had yielded a finished
                # InProgress, so we can iterate immediately and step back
                # into the coroutine.

        except StopIteration:
            # coroutine is done without result
            result = None
        except:
            # coroutine is done with exception
            return self.throw(*sys.exc_info())

        # Coroutine is done, stop and finish with its result (which may be
        # None if no result was explicitly yielded).
        self.stop()
        self.finish(result)
        return False


    def throw(self, *args):
        """
        Hook InProgress.throw to stop before finishing.  Allows a
        coroutine to be aborted asynchronously.
        """
        self.stop()
        return super(CoroutineLockedInProgress, self).throw(*args)


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
        if self in _active_coroutines:
            _active_coroutines.remove(self)

        # if this object waits for another CoroutineLockedInProgress, stop
        # that one, too.
        if isinstance(self._async, CoroutineLockedInProgress):
            self._async.stop()
        # Remove the internal timer, the async result and the
        # generator function to remove bad circular references.
        self._timer = None
        self._coroutine = None
        self._async = None


    def timeout(self, timeout):
        """
        Return an InProgress object linked to this one that will throw
        a TimeoutException if this object is not finished in time. If used,
        this will stop the coroutine.
        """
        return InProgress.timeout(self, timeout, callback=self.stop)


class CoroutineLockedInProgressLock(CoroutineLockedInProgress):
    """
    CoroutineLockedInProgress for handling locked coroutine functions.
    """
    def __init__(self, original_function, function, interval):
        CoroutineLockedInProgress.__init__(self, function, interval)
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
