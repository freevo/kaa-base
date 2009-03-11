InProgress Objects
==================

Throughout Kaa, when a function executes asynchronously (which is generally the
case for any function that may otherwise block on some resource), it returns an
InProgress object. The InProgress object is a signal that can be connected to
in order to handle its return value or any exception raised during the
asynchronous execution. When the InProgress object is emitted, we say that it
is "finished."

InProgress objects are emitted (they are Signal objects, remember)
when finished, so handlers can retrieve the return value of the
asynchronous task. There is also an exception member, which is itself
a Signal, and is emitted when the asynchronous task raises an
exception. Exception handlers must accept three arguments: exception
class, exception instance, and traceback object. InProgress objects
have the following methods:

.. kaaclass:: kaa.InProgress

   .. automethods::
      :remove: Progress

      .. method:: connect(callback, \*args, \*\*kwargs)

         connects a callback to be invoked when the InProgress has
         returned normally (no exception raised)

   .. autoproperties::
   .. autosignals::



InProgressAny
-------------

InProgressAny objects represent multiple InProgress objects, and is
finished when any one of the underlying InProgress objects
finishes. The object is finished with a 2-tuple (idx, result) where
idx is the index of the underlying finished InProgress (offset from 0
and in the order of the InProgress objects as passed to the
InProgressAny constructor), and where result is the result the
underlying InProgress finished with. If that InProgress was finished
by an exception, then result is a 3-tuple of (type, value, traceback)
representing the exception.

InProgressAll
-------------

InProgressAll objects represent multiple InProgress objects, and is
finished when all of the underlying InProgress objects are
finished. The InProgressAll object is always finished with itself
(that is in_progress_all.result == in_progress_all). The object is an
iterable, and will iterate over all of the InProgress objects passed
to its constructor.

__inprogress__
--------------

Similar to __len__ and len(), objects that implement the
__inprogress__ method (which takes no arguments) return an InProgress
object that represents the progress of the original object. There is a
method kaa.inprogress() which accepts an object and simply calls its
__inprogress__ method.

A practical demonstration of this protocol is in the Signal object,
which implements the __inprogress__ method. The returned InProgress in
that case is finished with the signal is next emitted. Any object
implementing the __inprogress__ protocol can be passed directly to the
constructor of InProgressAny or InProgressAll.

Coroutines
----------

A function or method is designated a coroutine by using the @kaa.coroutine
decorator.  A coroutine allows a larger tasks to be broken down into smaller
ones by yielding control back to the "scheduler" (the main loop), implementing
a kind of cooperative multitasking.  More usefully, coroutines can yield at
points where they may otherwise block on resources (e.g. disk or network), and
when the resource becomes available, the coroutine resumes where it left off.
With coroutines and InProgress objects, it is possible to construct non-trivial
state machines, whose state is modified by asynchronous events, using a single
coroutine.  Without coroutines, this is typically implemented as a series of
smaller callback functions.  (For more information on coroutines, see
`Wikipedia's treatment of the subject
<http://en.wikipedia.org/wiki/Coroutine>`_.)

Any function decorated with coroutine will return an InProgress object, and the
caller can connect a callback to the InProgress object in order to be notified
of its return value or any exception.

When a coroutine yields kaa.NotFinished, control is returned to the
main loop, and the coroutine will resume after the yield statement
at the next main loop iteration, or, if an interval is provided with the
decorator, after this time time interval.

When a coroutine yields any value other than kaa.NotFinished (including None),
the coroutine is considered finished and the InProgress returned to the caller
will be emitted (i.e. it is finished). As with return, if no value is
explicitly yielded and the coroutine terminates, the InProgress is finished
with None.  There is a single exception to this rule: if the coroutine yields
an InProgress object, the coroutine will be resumed when the InProgress object
is finished.

Here is a simple example that breaks up a loop into smaller tasks::

    import kaa

    @kaa.coroutine()
    def do_something():
       for i in range(10):
          do_something_expensive()
          yield kaa.NotFinished

    def handle_result(result):
       print "do_something() finished with result:", result

    do_something().connect(handle_result)
    kaa.main.run()

A coroutine can yield other coroutines (or rather, the InProgress
object the other coroutine returns)::

    @kaa.coroutine()
    def do_something_else():
       try:
          result = yield do_something()
       except:
          print "do_something failed"
          yield

       yield True if result else False

(Note that the above syntax, in which the yield statement returns a value,
was introduced in Python 2.5.  kaa.base requires Python 2.5 or later.)

Classes in kaa make heavy use of coroutines and threads when methods would
otherwise block on some resource.  Both coroutines and @threaded-decorated
methods return InProgress objects and behave identically.  These can be
therefore yielded from a coroutine in the same way::

    @kaa.coroutine()
    def fetch_page(host):
        """
        Fetches / from the given host on port 80.
        """
        socket = kaa.Socket()
        # Socket.connect() is implemented as a thread
        yield socket.connect((host, 80))
        # Socket.read() and write() are implemented as single-thread async I/O.
        yield socket.write('GET / HTTP/1.1\n\n')
        print (yield socket.read())

In the above example, the difference between threaded functions
(Socket.connect) and coroutines is transparent.  Both return InProgress
objects. (As an aside, we didn't really need to yield socket.write() because
writes are queued and written to the socket when it becomes writable.  However,
yielding a write means that when the coroutine resumes, the data has been
written.)
