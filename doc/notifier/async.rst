Asynchronous Programming
========================

One objective is avoid blocking the main loop for extended periods (in
order to improve interactivity and reduce latency), and kaa.base
provides two convenient approaches to accomplish this with
asynchronous programming: coroutines, and threads.

Coroutines are used to break up large and computationally expensive
tasks into smaller tasks, where control is relinquished to the main
loop after each smaller task. Coroutines are also very useful in
constructing state machines. In the event where blocking is
unavoidable, and the duration of the block is unknown (for example,
connecting to a remote host, or scaling a very large image), threads
can be used. These two different approaches are unified with a very
similar API.

InProgress Objects
------------------

Throughout Kaa, when a function executes asynchronously, it returns an
InProgress object. The InProgress object is a signal that can be
connected to in order to handle its return value or any exception
raised during the asynchronous execution. When the InProgress object
is emitted, we say that it is "finished."

InProgress objects are emitted (they are Signal objects, remember)
when finished, so handlers can retrieve the return value of the
asynchronous task. There is also an exception member, which is itself
a Signal, and is emitted when he asynchronous task raises an
exception. Exception handlers must accept three arguments: exception
class, exception instance, and traceback object. InProgress objects
have the following methods:

.. autoclass:: kaa.InProgress
    :members:

    .. method:: connect(callback, *args, **kwargs)

          connects a callback to be invoked when the InProgress has
          returned normally (no exception raised)



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

A function or method is designated a coroutine by using the coroutine
decorator. Any function decorated with coroutine will return an
InProgress object, and the caller can connect a callback to the
InProgress object in order to be notified of its return value or any
exception.

When a coroutine yields kaa.NotFinished, control is returned to the
main thread, and the coroutine will resume after the yield statement
at the next main loop iteration or if an interval is provided with the
decorator after this time time interval. When a coroutine yields any
value other than kaa.NotFinished (including None), the coroutine is
considered finished and the InProgress returned to the caller will be
emitted (i.e. it is finished). There is a single exception to this
rule: if the coroutine yields an InProgress object, the coroutine will
be resumed when the InProgress object is finished.

Here is a simple example that breaks up a loop into smaller tasks::

    import kaa

    @kaa.coroutine()
    def do_something():
       for i in range(10):
          do_something_expensive()
          yield kaa.NotFinished
       yield True

    def handle_result(result):
       print "do_something() finished with result:", result

    do_something().connect(handle_result)
    kaa.main.run()

A coroutine can yield other coroutines (or rather, the InProgress
object the other coroutine returns)::

    @kaa.coroutine()
    def do_something_else():
       progress = do_something()
       yield progress
       try:
          result = progress.get_result()
       except:
          print "do_something failed"
          yield

       if result == True:
          yield True
       yield False

In Python 2.5, it is possible for the yield statement itself to return
a value or raise an exception. This is supported as well::

    @kaa.coroutine()
    def do_something_else():
       try:
          result = yield do_something()
       except:
          print "do_something failed"
          yield

       yield True if result else False

Note that if you elect to use this idiom, your code will not run on
Python 2.4. (kaa.base itself supports Python 2.4, however, as this
syntax is not used internally.) Because of this idiom, in Python 2.5
the yield statement will raise an exception if there is one while
Python 2.4 continues and raises the exception when calling
get_result. That also means that none of the above two variants will
work perfectly with both Python versions, but one would have to wrap
the yield in the try/except block::

    @kaa.coroutine()
    def do_something_else():
       progress = do_something()
       try:
          yield progress                 # may throw in python 2.5
          result = progress.get_result() # may throw in python 2.4
       except:
          print "do_something failed"
          yield

       if result == True:
          yield True
       yield False

Note that the code becomes much more elegant if Python 2.4
compatibility is sacrificed.

With the help of InProgress objects, it is possible to construct
non-trivial state machines, whose state is modified by asynchronous
events, using a single coroutine.
