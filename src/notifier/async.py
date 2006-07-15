import logging

from callback import Signal

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
        if not self.exception_handler._callbacks:
            log.error('InProgress exception: %s', e)
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
