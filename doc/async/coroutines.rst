.. _coroutines:

Coroutines
----------

Coroutines are used to break up large and computationally expensive
tasks into smaller tasks, where control is relinquished to the main
loop after each smaller task. Coroutines are also very useful in
constructing state machines. In the event where blocking is
unavoidable, and the duration of the block is unknown (for example,
connecting to a remote host, or scaling a very large image), threads
can be used. These two different approaches are unified with a very
similar API.

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
`Wikipedia's treatment of the subject <http://en.wikipedia.org/wiki/Coroutine>`_.)

Any function decorated with coroutine will return an InProgress object, and the
caller can connect a callback to the InProgress object in order to be notified
of its return value or any exception.

When a coroutine yields kaa.NotFinished, control is returned to the
main loop, and the coroutine will resume after the yield statement
at the next main loop iteration, or, if an interval is provided with the
decorator, after this time interval.

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
       yield 42

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
