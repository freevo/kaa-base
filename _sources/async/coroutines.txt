.. module:: kaa.coroutine
   :synopsis: Functions that can yield and resume after some asynchronous
              task completes

.. _coroutines:

Coroutines
----------

Coroutines are special functions that have multiple entry points that allow
suspending and resuming execution at specified locations.  They allow you to:

 * write sequentially flowing code involving potentially blocking tasks (e.g.
   socket IO) that is actually completely non-blocking
 * "time slice" large, computationally expensive tasks to avoid blocking the
   mainloop for extended periods of time (which would prevent timers, IO
   handlers, and other coroutines from running)
 * help solve complex problems involving state `without using explicit state machines <http://eli.thegreenplace.net/2009/08/29/co-routines-as-an-alternative-to-state-machines/>`_

In the event where blocking is unavoidable, and the duration of the block is
unknown (for example, connecting to a remote host, or scaling a very large
image), threads can be used.  These two different approaches are unified with a
very similar API.

A function or method is designated a coroutine by using the ``@kaa.coroutine``
decorator.  A coroutine allows a larger tasks to be broken down into smaller
ones by yielding control back to the "scheduler" (the :ref:`notifier
<notifier>`), implementing a kind of cooperative multitasking.  More usefully,
coroutines can yield at points where they may otherwise block on resources
(e.g. disk or network), and when the resource becomes available, the coroutine
resumes where it left off.  Without coroutines, this is typically implemented
as a series of smaller callback functions.  (For more information on
coroutines, see `Wikipedia's treatment of the subject
<http://en.wikipedia.org/wiki/Coroutine>`_.)

Coroutines return an InProgress object, and the caller can connect a callback
to the InProgress object in order to be notified of its return value or any
exception, or it can yield the InProgress object from other coroutines.

When a coroutine yields ``kaa.NotFinished``, control is returned to the
main loop, and the coroutine will resume after the yield statement
at the next main loop iteration, or, if an interval is provided with the
decorator, after this time interval.  Following the cooperative multitasking
analogy, yielding ``kaa.NotFinished`` can be thought of as the coroutine releasing
a "time slice" so that other tasks may run.

When a coroutine yields any value other than ``kaa.NotFinished`` (including None),
the coroutine is considered finished and the InProgress returned to the caller
will be :ref:`emitted <emitting>` (i.e. it is finished). As with normal
function return values, if no value is explicitly yielded and the coroutine
terminates, the InProgress is finished with None.

There is an important exception to the above rule: if the coroutine yields an
:class:`~kaa.InProgress` object, the coroutine will be resumed when the
InProgress object is finished.  This allows a coroutine to be "chained" with
other InProgress tasks, including other coroutines.

To recap, if a coroutine yields:

 * ``kaa.NotFinished``: control is returned to the main loop so that other tasks
   can run (such as other timers, I/O handlers, etc.) and resumed on the next
   main loop iteration.
 * an :class:`~kaa.InProgress` object: control is returned to the main loop and
   the coroutine is resumed when the yielded InProgress is finished.  Inside
   the coroutine, the yield call "returns" the value that InProgress was finished
   with.
 * any other value: the coroutine terminates, and the InProgress the coroutine
   returned to the caller is finished with that value (which includes None, if
   no value was explicitly yielded and the coroutine reaches the end naturally).

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

Classes in kaa make heavy use of coroutines and (to a lesser extent) threads
when methods would otherwise block on some resource.  Both coroutines and
:ref:`@threaded <threaded>`-decorated methods return InProgress objects (well,
special subclasses of InProgress objects) and behave identically.  These can be
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
(:meth:`kaa.Socket.connect`) and coroutines (:meth:`~kaa.IOChannel.write` and
:meth:`~kaa.IOChannel.read`) is transparent.  Both return InProgress objects. (As
an aside, we didn't really need to yield socket.write() because writes are
queued and written to the socket when it becomes writable.  However, yielding a
write means that when the coroutine resumes, the data has been fully sent to the
socket.)

To more clearly see the benefit of implementing the above example as a coroutine,
consider the following code, which is rewritten using the more traditional approach
of connecting callbacks at the various stages of the task::

    def fetch_page(host):
        socket = kaa.Socket()
        socket.connect((host, 80)).connect(finished_connect, socket)

    def finished_connect(result, socket):
        socket.write('GET / HTTP/1.1\n\n').connect(finished_write, socket)

    def finished_write(len, socket):
        socket.read().connect(finished_read)

    def finished_read(data):
        print data


In practice then, coroutines can be seen as an alternative approach to the
classic signal/callback pattern, allowing you to achieve the same logic but
with a much more intuitive and readable code.  This means that if you design
your application to use signals and callbacks, it might not be clear where
coroutines would be useful.

However, if you make use of the asynchronous plumbing that kaa offers early on
in your design -- and that includes liberal use of :class:`~kaa.InProgress`
objects, either explicitly or implicitly through the use of the
:ref:`@coroutine <coroutine>` and :ref:`@threaded <threaded>` decorators -- you
should find that you're able to produce some surprisingly elegant, non-trivial
code.


Aborting Coroutines
===================

Coroutines that have yielded and are awaiting reentry can be aborted by calling
the :meth:`~kaa.CoroutineInProgress.abort` method on the
:class:`~kaa.CoroutineInProgress` object returned when invoking a coroutine.
Consider this simple case::

    @kaa.coroutine()
    def delay_print(s):
        yield kaa.delay(5)
        print s

    delay_print('Hello Kaa').abort()
    kaa.main.run()

When aborted, an :class:`~kaa.InProgressAborted` exception will be raised inside
the coroutine.  If the exception is not caught, then it is raised back to the
caller of :meth:`~kaa.CoroutineInProgress.abort`.  In the above example, because
``delay_print`` doesn't catch any exception, abort() will raise.  The
coroutine can catch the exception and do something suitable::

    @kaa.coroutine()
    def delay_print(s):
        try:
            yield kaa.delay(5)
        except kaa.InProgressAborted as e:
            # Nothing special needed to abort this.
            pass
        else:
            print s

The :class:`~kaa.InProgressAborted` exception object has an
:attr:`~kaa.InProgressAborted.inprogress` attribute, which will always be the
:class:`~kaa.InProgress` object of the yielded task (or none if
``kaa.NotFinished`` was yielded), and an :attr:`~kaa.InProgressAborted.origin`
attribute that is the :class:`~kaa.InProgress` of the task that abort() was
called on.

Provided it is :attr:`~kaa.InProgress.abortable` and nothing else but the
coroutine being aborted is waiting on it, any :class:`~kaa.InProgress` task
yielded by a coroutine will be aborted before the exception is raised inside
the function.  So in the above example, ``e.inprogress`` refers to the
:class:`~kaa.InProgress` object returned by :func:`kaa.delay` and
``e.inprogress.finished`` will be True.

This cascading abort can be prevented by the coroutine by instead yielding an
unabortable version of the InProgress using :meth:`~kaa.InProgress.noabort`::

    @kaa.coroutine()
    def delay_print(s):
        try:
            yield kaa.delay(5).noabort()
        except kaa.InProgressAborted as e:
            print e.inprogress.finished, 'will be false'
        else:
            print s

This means :func:`kaa.delay` in the above example will live on even when
``delay_print`` is aborted.  (Not that it does any good in this contrived example,
since the timer will fire and do nothing, but you get the idea.)

Although it can catch the :class:`~kaa.InProgressAborted`, the coroutine is
still considered aborted and it will not be reentered again.  If it attempts to
yield a value that suggests it expects reentry (like ``kaa.NotFinished`` or an
:class:`~kaa.InProgress`) then a ``RuntimeError`` will be raised.  There is
nothing a coroutine can do to prevent its own demise.  But a coroutine ``a()``
that yields another coroutine ``z()`` can prevent ``z()`` from being aborted when
``a()`` is aborted by using :meth:`~kaa.InProgress.noabort`.

If a coroutine yields a task that is aborted, then an :class:`~kaa.InProgressAborted`
will also be raised inside the coroutine whose yielded task was aborted.  The
:attr:`~kaa.InProgressAborted.origin` attribute will indicate the task that was the
source of the abort::

    @kaa.coroutine(policy=kaa.POLICY_SINGLETON)
    def singleton():
        try:
            yield kaa.delay(5)
        except kaa.InProgressAborted as e:
            print 'singleton() aborted'

    @kaa.coroutine()
    def master():
        try:
            yield singleton()
        except kaa.InProgressAborted as e:
            print 'master() aborted because %s aborted' % e.origin

    master()
    kaa.OneShotTimer(singleton().abort).start(1)


Decorator
=========

.. _coroutine:

.. autofunction:: kaa.coroutine

.. kaaclass:: kaa.CoroutineInProgress
   :synopsis:

   .. automethods::
      :remove: throw
   .. autoproperties::
   .. autosignals::
