.. module:: kaa.thread
   :synopsis: Threaded tasks managed through InProgress objects
.. _threads:

Thread Support
==============

.. _threaded:

The threaded decorator
----------------------

Any function or method may be decorated with ``@kaa.threaded()`` which takes
two optional arguments: a thread name, and a priority. If a thread name is
specified, the decorated function is wrapped in
:class:`~kaa.ThreadPoolCallable`, and invocations of that function are queued
to be executed across one or more threads. If the thread name is ``kaa.MAINTHREAD`` the
decorated function is invoked from the main thread. If no thread name is
specified, the function is wrapped in :class:`~kaa.ThreadCallable` so that each
invocation is executed in a separate thread. Because these callables return
:class:`~kaa.ThreadInProgress` objects, which are derived from
:class:`~kaa.InProgress`, they may be yielded from :ref:`coroutines <coroutines>`.

For example::

  @kaa.threaded()
  def do_blocking_task():
     [...]
     return 42

  @kaa.coroutine()
  def do_something_else():
     try:
        result = yield do_blocking_task()
     except:
        print "Exception raised in thread"

     print "Thread returned", result

The threaded decorator also supports a async kwarg, which is by default True.
When True, the decorated function returns a :class:`~kaa.ThreadInProgress`
object. When False, however, invocation of the function blocks until the
decorated function completes, and its return value is passed back.  Internally,
the decorator merely invokes :meth:`~kaa.InProgress.wait` on the InProgress
returned by the threaded function, which means the main loop is otherwise kept
alive for timers and I/O handlers.  This allows a threaded function to be used
as a standard callback (but in practice it is not used often).

.. autofunction:: kaa.threaded

As a rule of thumb, if you have a function that must always be called
in the main thread, you would use ``@kaa.threaded(kaa.MAINTHREAD)`` as
mentioned above. If you need to decide case-by-case, don't decorate it
and use :class:`~kaa.MainThreadCallable` when needed.


The synchronized decorator
--------------------------

.. autoclass:: kaa.synchronized

Some functions may need to block concurrent access to certain
data structures, or prevent concurrent entry to the whole function.  In these
cases, ``kaa.synchronized`` can be used, which serves as both a decorator as
well as a context manager for use with Python's ``with`` statement::
   
    class Test(object):

        def foo(self):
            # call to do_something() can be done concurrently by other threads.
            do_something()
            with kaa.synchronized(self):
                # Anything in this block however is synchronized between threads.
                do_something_else()


        # bar() is a protected function
        @kaa.synchronized()
        def bar(self, x, y):
            do_something_else()

The decorator will synchronize on the actual object. Two different
objects can access the same function in two threads. On the other hand
it is not possible that one thread is in the protected block of `foo`
and another one calling `bar`.

The decorator can also be used for functions outside a class. In that
case the decorator only protects this one function. If more functions
should be protected against each other, a Python RLock object can be
provided::

  # threading.Lock does NOT work
  lock = threading.RLock()

  @kaa.synchronized(lock)
  def foo():
      # foo and bar synchronized
      do_something()

  @kaa.synchronized(lock)
  def bar(x):
      # foo and bar synchronized
      do_something()

  @kaa.synchronized()
  def baz():
      # only_baz_synchronized
      do_something()



Thread Functions
----------------

The following thread-related functions are available:

.. autofunction:: kaa.is_mainthread

.. autofunction:: kaa.main.wakeup

.. autofunction:: kaa.register_thread_pool

.. autofunction:: kaa.get_thread_pool


Callables and Supporting Classes
--------------------------------

Kaa provides a :class:`~kaa.ThreadCallable` class which can be used to invoke a
callable in a new thread every time the ThreadCallable object is invoked.

With the :class:`~kaa.ThreadPoolCallable` class, invocations are queued and
each executed in an available thread within a pool of one or more threads. A
priority may also be specified, and ThreadPoolCallable objects with the highest
priority are first in the queue (and hence executed first). This allows you to
create a priority-based job queue that executes asynchronously.

Although the :func:`@kaa.threaded() <kaa.threaded>` decorator provides a more
convenient means to make use of these classes, they may still be used directly.

Instances of the two classes above are callable, and they return
:class:`~kaa.ThreadInProgress` objects::

    def handle_result(result):
        # This runs in the main thread.
        print 'Thread returned with', result

    kaa.ThreadCallable(do_blocking_task)(arg1, arg2).connect(handle_result)

Or, alternatively::

    @kaa.coroutine()
    def some_coroutine():
        [...]
        result = yield kaa.ThreadCallable(do_blocking_task)(arg1, arg2)
    

.. kaaclass:: kaa.ThreadInProgress
   :synopsis:

   .. automethods::
      :remove: active
   .. autoproperties::

.. kaaclass:: kaa.ThreadCallable
   :synopsis:

   .. automethods::
   .. autoproperties::
   .. autosignals::

.. kaaclass:: kaa.ThreadPool
   :synopsis:

   .. automethods::
   .. autoproperties::
   .. autosignals::

.. kaaclass:: kaa.ThreadPoolCallable
   :synopsis:

   .. automethods::
   .. autoproperties::
   .. autosignals::


.. kaaclass:: kaa.MainThreadCallable

   The MainThreadCallable ensures that the wrapped function or method is executed
   via main loop.  The thread calling this function will return immediately after
   calling the MainThreadCallable, without waiting for the result. Invoking
   MainThreadCallables always returns an InProgress object::
   
     def needs_to_be_called_from_main(param):
         print param
         return 5
   
     # ... suppose we are in a thread here ...
     cb = kaa.MainThreadCallable(needs_to_be_called_from_main)
     print cb(3).wait()

   .. autosynopsis::

      .. automethods::
      .. autoproperties::
      .. autosignals::

