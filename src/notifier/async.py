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

__all__ = [ 'TimeoutException', 'InProgress', 'InProgressCallback', 'AsyncException',
            'AsyncExceptionBase', 'make_exception_class' ]

# python imports
import sys
import logging
import traceback
import time
import _weakref
import threading
import types

# kaa.notifier imports
from callback import Callback
from signals import Signal

# get logging object
log = logging.getLogger('notifier.async')


def make_exception_class(name, bases, dict):
    """
    Class generator for AsyncException.  Creates AsyncException class
    which derives the class of a particular Exception instance.
    """
    def create(exc, stack, *args):
        from new import classobj
        dict.update({
            # Necessary for python 2.4
            '__str__': AsyncExceptionBase.__str__
        })
        e = classobj(name, (exc.__class__,) + bases, dict)(*exc.args)
        e._set_info(exc.__class__.__name__, stack, *args)
        return e

    return create


class AsyncExceptionBase(Exception):
    """
    Base class for asynchronous exceptions.  This class can be used to raise
    exceptions where the traceback object is not available.  The stack is
    stored (which is safe to reference and can be pickled) instead, and when
    AsyncExceptionBase instances are printed, the original traceback will
    be printed.
    """
    def _set_info(self, exc_name, stack, *args):
        self._kaa_exc_name = exc_name
        self._kaa_exc_stack = stack
        self._kaa_exc_args = args

    def _get_header(self):
        return 'Exception raised asynchronously; traceback follows:'

    def __str__(self):
        dump = ''.join(traceback.format_list(self._kaa_exc_stack))
        # Python 2.5 always has self.message; for Python 2.4, fall back to
        # first argument if it's a string.
        msg = (hasattr(self, 'message') and self.message) or \
              (self.args and isinstance(self.args[0], basestring) and self.args[0])
        if msg:
            info = '%s: %s' % (self._kaa_exc_name, msg)
        else:
            info = self._kaa_exc_name

        return self._get_header() + '\n' + dump + info


class AsyncException(AsyncExceptionBase):
    __metaclass__ = make_exception_class


class TimeoutException(Exception):
    pass


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
        self._finished_event = threading.Event()
        self._unhandled_exception = None
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
        # XXX: Temporary wrapper for deprecated method name.
        log.warning('InProgress.finished() deprecated; use InProgress.finish()')
        return self.finish(result)


    def finish(self, result):
        """
        This function should be called when the creating function is
        done and no longer in progress.
        """
        if isinstance(result, InProgress):
            # we are still not finished, link to this new InProgress
            self.link(result)
            return

        # store result
        self._finished = True
        self._result = result
        self._exception = None
        # Wake any threads waiting on us
        self._finished_event.set()
        # emit signal
        self.emit_when_handled(result)
        # cleanup
        self.disconnect_all()
        self.exception.disconnect_all()


    def throw(self, type, value, tb):
        """
        This function should be called when the creating function is
        done because it raised an exception.
        """
        # This function must deal with a tricky problem.  See:
        # http://mail.python.org/pipermail/python-dev/2005-September/056091.html
        #
        # Ideally, we want to store the traceback object so we can defer the
        # exception handling until some later time.  The problem is that by
        # storing the traceback, we create some ridiculously deep circular
        # references.
        #
        # The way we deal with this is to pass along the traceback object to
        # any handler that can handle the exception immediately, and then
        # discard the traceback.  A stringified formatted traceback is attached
        # to the exception in the formatted_traceback attribute.
        #
        # The above URL suggests a possible non-trivial workaround: create a
        # custom traceback object in C code that preserves the parts of the
        # stack frames needed for printing tracebacks, but discarding objects
        # that would create circular references.  This might be a TODO.

        self._finished = True
        self._exception = type, value, tb
        self._unhandled_exception = True
        stack = traceback.extract_tb(tb)

        # Attach a stringified traceback to the exception object.  Right now,
        # this is the best we can do for asynchronous handlers.
        trace = ''.join(traceback.format_exception(*self._exception)).strip()
        value.formatted_traceback = trace

        # Wake any threads waiting on us.  We've initialized _exception with
        # the traceback object, so any threads that call get_result() between
        # now and the end of this function will have an opportunity to get
        # the live traceback.
        self._finished_event.set()

        if self.exception.count() == 0:
            # There are no exception handlers, so we know we will end up
            # queuing the traceback in the exception signal.  Set it to None
            # to prevent that.
            tb = None

        if self.exception.emit_when_handled(type, value, tb) == False:
            # A handler has acknowledged handling this exception by returning
            # False.  So we won't log it.
            self._unhandled_exception = None

        if self._unhandled_exception:
            # This exception was not handled synchronously, so we set up a
            # weakref object with a finalize callback to a function that
            # logs the exception.  We could do this in __del__, except that
            # the gc refuses to collect objects with a destructor.  The weakref
            # kludge lets us accomplish the same thing without actually using
            # __del__.
            #
            # If the exception is passed back via get_result(), then it is
            # considered handled, and it will not be logged.
            cb = Callback(InProgress._log_exception, trace, value)
            self._unhandled_exception = _weakref.ref(self, cb)

        # Remove traceback from stored exception.  If any waiting threads
        # haven't gotten it by now, it's too late.
        self._exception = type, value, stack

        # cleanup
        self.disconnect_all()
        self.exception.disconnect_all()


    @classmethod
    def _log_exception(cls, weakref, trace, exc):
        """
        Callback to log unhandled exceptions.
        """
        if isinstance(exc, (SystemExit, KeyboardInterrupt)):
            # We have an unhandled asynchronous SystemExit or KeyboardInterrupt
            # exception.  Rather than logging it, we reraise it in the main
            # loop so that the main loop exception handler can act
            # appropriately.
            import main
            def reraise():
                raise exc
            return main.signals['step'].connect_once(reraise)

        log.error('Unhandled %s exception:\n%s', cls.__name__, trace)


    def execute(self, func, *args, **kwargs):
        """
        Execute the function and store the result or exception inside the
        InProgress object. Returns self to support yield in a coroutine.
        To yield a finished object call yield InProgress().execute(...)
        """
        try:
            result = func(*args, **kwargs)
        except:
            self.throw(*sys.exc_info())
        else:
            self.finish(result)
        return self


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
            self._unhandled_exception = None
            exc_type, exc_value, exc_tb_or_stack = self._exception
            if type(exc_tb_or_stack) == types.TracebackType:
                # We have the traceback, so we can raise using it.
                raise exc_type, exc_value, exc_tb_or_stack
            else:
                # No traceback, so construct an AsyncException based on the
                # stack.
                if not isinstance(exc_value, AsyncExceptionBase):
                    exc_value = AsyncException(exc_value, exc_tb_or_stack)
                raise exc_value

        return self._result


    def wait(self, timeout = None):
        """
        Waits for the result (or exception) of the InProgress object.  The
        main loop is kept alive if waiting in the main thread, otherwise
        the thread is blocked until another thread finishes the InProgress.

        If timeout is specified, wait() blocks for at most timeout seconds
        (which may be fractional).  If wait times out, a TimeoutException is
        raised.
        """
        # Import modules here rather than globally to avoid circular importing.
        import main
        from thread import set_as_mainthread, is_mainthread

        if not main.is_running():
            # No main loop is running yet.  We're calling step() below,
            # but we won't get notified of any thread completion
            # unless the thread notifier pipe is initialized.
            set_as_mainthread()

        if is_mainthread():
            # We're waiting in the main thread, so we must keep the mainloop
            # alive by calling step() until we're finished.
            abort = []
            if timeout:
                # Add a timer to make sure the notifier doesn't sleep
                # beyond out timeout.
                from timer import OneShotTimer
                OneShotTimer(lambda: abort.append(True)).start(timeout)

            while not self.is_finished() and not abort:
                main.step()
        else:
            # We're waiting in some other thread, so wait for some other
            # thread to wake us up.
            self._finished_event.wait(timeout)

        if not self.is_finished():
            raise TimeoutException

        return self.get_result()


    def link(self, in_progress):
        """
        Links with another InProgress object.  When the supplied in_progress
        object finishes (or throws), we do too.
        """
        in_progress.connect_both(self.finish, self.throw)


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
        self.exception.connect_once(exception)



class InProgressCallback(InProgress):
    """
    InProgress object that can be used as a callback for an async
    function. The InProgress object will be finished when it is
    called. Special support for Signals that will finish the InProgress
    object when the signal is emited.
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
        Call the InProgressCallback by the external function. This will
        finish the InProgress object.
        """
        # try to get the results as the caller excepts them
        if args and kwargs:
            # no idea how to merge them
            return self.finish((args, kwargs))
        if kwargs and len(kwargs) == 1:
            # return the value
            return self.finish(kwargs.values()[0])
        if kwargs:
            # return as dict
            return self.finish(kwargs)
        if len(args) == 1:
            # return value
            return self.finish(args[0])
        if len(args) > 1:
            # return as list
            return self.finish(args)
        return self.finish(None)
