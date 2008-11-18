Thread Support
==============

FIXME: this section is just copied from the Wiki

ThreadCallback
--------------

Kaa provides a ThreadCallback class which can be used to invoke a
callback in a new thread every time the ThreadCallback object is
invoked.

With the NamedThreadCallback class, invocations are queued and each
executed in the same thread. A priority may also be specified, and
NamedThreadCallback objects with the highest priority is first in the
queue (and hence executed first). This allows you to create a
priority-based job queue that executes asynchronously.

Instances of the two classes above are callable, and they return
InProgress objects::

  def handle_result(result):
     print "Thread returned with", result

  kaa.ThreadCallback(do_blocking_task)(arg1, arg2).connect(handle_result)


.. autoclass:: kaa.ThreadCallback
.. autoclass:: kaa.NamedThreadCallback

The MainThreadCallback is a callback that will be executed from the
main loop. The thread calling this function will return immediately
after calling the object without waiting for the result. Invoking
MainThreadCallbacks always returns an InProgress object::

  def needs_to_be_called_from_main(param):
      print param
      return 5

  # ... suppose we are in a thread here ...
  cb = kaa.MainThreadCallback(needs_to_be_called_from_main)
  print cb(3).wait()

As a rule of thumb, if you have a function that must always be called
in the main thread, you would use @kaa.threaded(kaa.MAINTHREAD) as
mentioned above, if you need to decide case-by-case, don't decorate it
and use MainThreadCallback when needed.

.. autoclass:: kaa.MainThreadCallback


The threaded decorator
----------------------

Any function or method may be decorated with @kaa.threaded() which
takes two optional arguments: a thread name, and a priority. If a
thread name is specified, the decorated function is wrapped in
NamedThreadCallback, and invocations of that function are queued to be
executed in a single thread. If the thread name is kaa.MAINTHREAD the
decorated function is invoked from the main thread. If no thread name
is specified, the function is wrapped in ThreadCallback so that each
invocation is executed in a separate thread. Because these callbacks
returns InProgress objects, they may be yielded from coroutines.

(This example uses Python 2.5 syntax.)::

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

The @kaa.threaded decorator also supports a async kwarg, which is by
default True. When True, the decorated function returns an InProgress
object. When False, however, invocation of the function blocks until
the decorated function completes, and its return value is passed
back. This allows a threaded function to be used as a standard
callback.

.. autofunction:: kaa.threaded


Helper Functions
----------------

.. autofunction:: kaa.is_mainthread
.. autofunction:: kaa.notifier.main.wakeup
.. autoclass:: kaa.synchronized

Generic Mainloop and GObject Interaction
----------------------------------------

FIXME: this section is not yet written

.. autofunction:: kaa.gobject_set_threaded
