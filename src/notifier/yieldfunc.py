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

__all__ = [ 'YieldContinue', 'YieldCallback', 'yield_execution',
            'YieldFunction' ]

import sys
import logging

from callback import Signal
from timer import Timer
from async import InProgress

log = logging.getLogger('notifier.yield')

# XXX YIELD CHANGES NOTES
# XXX Not possible to remove that and replace it with None because a
# XXX function may want to return None. Using return does not help here.
YieldContinue = object()

# XXX YIELD CHANGES NOTES
# XXX The deferrer stuff from Signal and InProgress won't work because
# XXX some parts connect interally to the InProgress object returned
# by yield_execution and the deferrer only handles one connect!


class YieldCallback(InProgress):
    """
    Callback class that can be used as a callback for a function that is
    async. Return this object using 'yield' and use the member function
    'get' later to get the result.
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


    def get(self):
        log.warning('Deprecated call to YieldCallback.get(); use get_result() instead')
        return InProgress.get_result(self)
        

# variable to detect if send is possible with a generator
# XXX This breaks existing code because now the exception is raised inside
# XXX the yield call while this was safe until now, only get_result() could
# XXX crash before that. After checking the code, _python25 should be set to
# _python25 = sys.version.split()[0] > '2.4'
_python25 = False

def _process(func, async=None):
    """
    function to call next, step, or throw
    """
    if _python25 and async is not None:
        if async._exception:
            e = async._exception
            return func.throw(e.__class__, e)
        return func.send(async._result)
    return func.next()


def yield_execution(interval=0, lock=False):
    """
    Functions with this decorator uses yield to break and to return the
    results. Special yield values for break are YieldContinue or
    InProgress objects. In lock is True the function will
    be locked against parallel calls. If locked the call will delayed.
    A function decorated with this decorator will always return a
    YieldFunction (which is an InProgress object) or the result.
    XXX YIELD CHANGES NOTES
    XXX This function will always return YieldFunction or an already
    XXX finished InProgress object in the future.
    """
    def decorator(func):

        def newfunc(*args, **kwargs):
            result = func(*args, **kwargs)
            if not hasattr(result, 'next'):
                # Decorated function doesn't have a next attribute, which
                # likyle means it didn't yield anything.  There was no sense
                # in decorating that function with yield_execution, but on
                # the other hand it's easy enough just to return the result.
                # XXX YIELD CHANGES NOTES
                # XXX Create InProgress object here and emit delayed
                # XXX result After that, return that InProgress object
                # XXX to always return an InProgress object.
                return result
            function = result
            if lock and func._lock is not None and not func._lock.is_finished:
                return YieldLock(func, function, interval)
            try:
                result = _process(function)
            except StopIteration:
                # no return with yield, but done, return None
                # XXX YIELD CHANGES NOTES
                # XXX Create InProgress object here and emit delayed
                # XXX result After that, return that InProgress object
                # XXX to always return an InProgress object.
                return None
            if not (result == YieldContinue or isinstance(result, InProgress)):
                # everything went fine, return result
                # XXX YIELD CHANGES NOTES
                # XXX Create InProgress object here and emit delayed
                # XXX result After that, return that InProgress object
                # XXX to always return an InProgress object.
                return result
            # we need a step callback to finish this later
            # result is one of YieldContinue, InProgress
            progress = YieldFunction(function, interval, result)
            if lock:
                func._lock = progress
            # return the YieldFunction (InProgress)
            return progress

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
    for yield_execution if it takes some more time. status can be either None
    (not started yet), YieldContinue (iterate now) or InProgress (wait until
    InProgress is done).
    """
    def __init__(self, function, interval, status=None):
        InProgress.__init__(self)
        self._yield__function = function
        self._timer = Timer(self._step)
        self._interval = interval
        if status == None:
            # No status from yield_execution, this means that the YieldFunction
            # was created from the outside and the creator must call this object
            self._valid = False
            return
        self._valid = True
        self._async = None
        if status == YieldContinue:
            # yield_execution was stopped YieldContinue, start the step timer
            self._timer.start(interval)
        elif isinstance(status, InProgress):
            # continue when InProgress is done
            # XXX YIELD CHANGES NOTES
            # XXX Be careful with already finished InProgress
            self._async = status
            status.connect_both(self._continue, self._continue)
        else:
            raise RuntimeError('YieldFunction with bad status %s' % status)


    def __call__(self, *args, **kwargs):
        """
        Call the YieldFunction to start it if it was not created by
        yield_execution.
        """
        if not self._valid:
            # The generator was not started yet
            self._valid = True
            self._yield__function = self._yield__function(*args, **kwargs)
            self._continue()
            return True
        # return the result
        log.warning('Deprecated call to InProgress(); use get_result() instead')
        return InProgress.get_result(self)


    def _continue(self, *args, **kwargs):
        """
        Restart timer.
        """
        if self._timer:
            # continue calling _step
            self._timer.start(self._interval)


    def _step(self):
        """
        Call next step of the yield function.
        """
        try:
            result = _process(self._yield__function, self._async)
        except (SystemExit, KeyboardInterrupt):
            self._timer.stop()
            self._async = None
            self._yield__function = None
            sys.exit(0)
        except StopIteration:
            result = None
        except Exception, e:
            # YieldFunction is done with exception
            e._exc_info = sys.exc_info()
            self._timer.stop()
            self._async = None
            self._yield__function = None
            self.throw(e)
            return False
        if result == YieldContinue:
            # schedule next interation with the timer
            return True
        # We have to stop the timer because we either have a result
        # or have to wait for an InProgress
        self._timer.stop()
        if isinstance(result, InProgress):
            # continue when InProgress is done
            # XXX YIELD CHANGES NOTES
            # XXX Remember result for Python 2.5 to send back
            # XXX Be careful with already finished InProgress
            self._async = result
            result.connect_both(self._continue, self._continue)
            return False
        # YieldFunction is done
        self._timer = None
        self.finished(result)
        self._async = None
        self._yield__function = None
        return False


    def stop(self):
        """
        Stop the function, no callbacks called.
        """
        if self._timer and self._timer.active():
            self._timer.stop()
        self._timer = None
        self._yield__function = None
        self._async = None


class YieldLock(YieldFunction):
    """
    YieldFunction for handling locked yield_execution functions.
    """
    def __init__(self, original_function, function, interval):
        YieldFunction.__init__(self, function, interval)
        self._func = original_function
        self._func._lock.connect_both(self._try_again, self._try_again)


    def _try_again(self, result):
        """
        Try to start now.
        """
        if not self._func._lock.is_finished:
            # still locked by a new call, wait again
            self._func._lock.connect_both(self._try_again, self._try_again)
            return
        self._func._lock = self
        self._continue()
