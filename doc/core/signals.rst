.. _callables:

Signals and Callables
=====================

Signal and Callable objects are among the core building blocks of Kaa and are
used extensively throughout the framework.

.. module:: kaa.callable
   :synopsis: Encapsulate functions or methods and arguments into a callable


Callables
---------

Callable objects encapsulate a callable (such as a function or method) and,
optionally, any number of arguments and keyword arguments.  Callable objects
are in turn invokable like any other native callable, and upon invocation will
call the underlying (wrapped) function or method, passing it all arguments
passed during invocation combined with all arguments passed to the constructor.

One very common use-case of Callable objects is any time a callback function is
required, such as with signals (described later).  They can be used to construct
partial functions::

    >>> square = kaa.Callable(pow, 2)
    >>> print square(5)
    25

(Of course this example is a bit contrived, because you could use lambda to
achieve the same result with less overhead.  But it helps to start simple.)

By default, all arguments passed upon invocation of the Callable are passed to the
wrapped callable first, followed by arguments passed upon construction.  So the
above example translates to ``pow(5, 2)``.  It is possible to reverse this behaviour
by setting the :attr:`~kaa.Callable.init_args_first` property to True::

    >>> square.init_args_first = True
    >>> square(5)  # Of course, now this isn't a square
    32

Keyword arguments work in a similar way.  Keyword arguments given to the
constructor as well as those passed upon invocation are passed to the
wrapped callable.  When ``init_args_first`` is ``False`` (default), keyword
arguments passed on invocation take precedence (overwrite) same-named keyword
arguments passed on the constructor.  When ``True``, keyword arguments from the
constructor take precedence over those passed upon invocation.

Here's an example that more clearly demonstrates the rules of precedence::

    >>> def func(*args, **kwargs):
    ...     print 'Callable:', args, kwargs
    ... 
    >>> cb = kaa.Callable(func, 1, 2, foo=42, bar='kaa')
    >>> cb()
    Callable: (1, 2) {'foo': 42, 'bar': 'kaa'}
    >>> cb('hello world', foo='overrides', another='kwarg')
    Callable: ('hello world', 1, 2) {'foo': 'overrides', 'bar': 'kaa', 'another': 'kwarg'}
    >>> cb.init_args_first = True
    >>> cb('hello world', foo="doesn't override", another='kwarg')
    Callable: (1, 2, 'hello world') {'foo': 42, 'bar': 'kaa', 'another': 'kwarg'}


Because Callable objects hold references to the function, or to the class
instance in the case of a method, and any arguments passed at construction
time, those objects remain alive as long as the Callable is referenced.  This
is not always what's wanted, and in those cases the :class:`~kaa.WeakCallable`
variant can be used.

With :class:`~kaa.WeakCallable`, only weak references are held to the callable
and constructor arguments.  When any of the wrapped objects are destroyed,
the WeakCallable ceases to be valid.  One common use-case for WeakCallable
is to avoid cyclical references.  For example, an object may hold an
:class:`~kaa.IOMonitor` on some file descriptor, and have a method invoked
when there's activity.  Consider this code fragment::

    class MyClass(object):
        def __init__(self, fd):
            self._monitor = kaa.IOMonitor(self._handle_read)
            self._monitor.register(fd)

In this example, a reference cycle is created: the MyClass instance holds
a reference to the IOMonitor, which holds a reference to the _handle_read method
of the MyClass instance (which implicitly holds a reference to the MyClass instance
itself).

You might be thinking this isn't a problem: after all, Python has a garbage
collector that will detect and break orphaned cyclic references.  However,
because the file descriptor ``fd`` is registered (with the :ref:`notifier
<notifier>`), Kaa keeps an internal reference to the IOMonitor.  Therefore,
even if all user-visible references to the MyClass instance are gone, neither
that object nor the IOMonitor ever get deleted (at least so long as the fd is
open).  And furthermore, ``MyClass._handle_read()`` will continue to be invoked
upon activity of the fd.

If you want the IOMonitor to automatically become unregistered when the callback
(or specifically the instance the method belongs to) is destroyed, you can use a
WeakCallable::

    self._monitor = kaa.IOMonitor(kaa.WeakCallable(self._handle_read))

In this example, when the :ref:`notifier <notifier>` would normally invoke the
callback (when there is activity on the registered file descriptor), it will
find the weak callable is in fact dead and automatically unregister the
monitor.  With this, the instance of MyClass is allowed to be destroyed (at
least insofar as Kaa would not hold any internal references to it).

Now, the previous example is a bit clumsy because it requires the callback
to be invoked (or attempted to be) before the monitor is automatically 
unregistered.  It would be cleaner if the monitor was registered immediately
when the MyClass instance is destroyed.  For this, the weak variant of IOMonitor
called WeakIOMonitor can be used::

    self._monitor = kaa.WeakIOMonitor(self._handle_read)

Weak variants of these :ref:`notifier <notifier>`-aware classes exist
throughout Kaa: :class:`~kaa.WeakIOMonitor`, :class:`~kaa.WeakTimer`,
:class:`~kaa.WeakOneShotTimer`, :class:`~kaa.WeakEventHandler`.



Callable API
~~~~~~~~~~~~

.. kaaclass:: kaa.Callable
   :synopsis:

   .. automethods::
      :add: __call__

   .. autoproperties::
      :remove: user_args_first


.. kaaclass:: kaa.WeakCallable
   :synopsis:

   .. autoproperties::


.. _signals:

Signals
-------

.. _emitting:

In Kaa, signals don't refer to Unix signals, but rather are similar to gtk+ signals
in that they are hooks to allow you to connect callbacks to be triggered when
certain events occur.  A signal may have any number of callbacks connected to it,
and when it is *emitted*, all the callbacks are invoked.  For example,
:class:`kaa.IOChannel` has a signal called :attr:`~kaa.IOChannel.signals.read`
which is emitted when a chunk of data has been read from the IO channel.

Classes that offer signals have a *signals* attribute, which is a dictionary
(or in fact a :class:`kaa.Signals` object, which behaves like a dictionary), whose
keys are the names of the signal supported by that object, and the corresponding
values are :class:`kaa.Signal` objects.  For example::

    def handle_data_chunk(data, userdata):
        print 'Read:', data

    iochannel.signals['read'].connect(handle_data_chunk, 'This is user data')

The :meth:`~kaa.Signal.connect` method accepts a callable and arbitrary
non-keyword and keyword arguments, which are passed to the callback.  This
method, and the whole ``connect_*`` family of methods in general, constructs a
:class:`~kaa.Callable` object implicitly (and in fact return that newly
constructed Callable).  So the above example is equivalent to::

    iochannel.signals['read'].connect(kaa.Callable(handle_data_chunk, 'this is user data'))

Obviously the earlier form is more convenient.  Similarly, :meth:`~kaa.Signal.connect_weak`
does the same thing, except it creates a :class:`~kaa.WeakCallable` from the callback and
arguments.

It is possible to detect when a Signal changes by assigning a callback to the Signal
object's :attr:`~kaa.Signal.changed_cb` property (or by passing it on the constructor)::

    >>> def signal_changed(signal, action):
    ...     if action == kaa.Signal.CONNECTED:
    ...         print 'New callback added, signal now has %d' % len(signal)
    ...     else:
    ...         print 'Callback removed, signal now has %d' % len(signal)
    ... 
    >>> sig = kaa.Signal(changed_cb=signal_changed)
    >>> callback = sig.connect(lambda: None)
    New callback added, signal now has 1
    >>> sig.disconnect(callback)
    Callback added, signal now has 0

One example of where this is used is with IOChannel's
:attr:`~kaa.IOChannel.signals.read` signal.  If there are no callbacks
connected to the ``read`` signal then we don't want to consume any data
from the channel.  So, when a callback is connected, the IOChannel must
register itself with the :ref:`notifier <notifier>` and handle read events in
order to consume data, passing it to all the callbacks connected to the read
signal.  When all callbacks have been disconnected, the IOChannel must
unregister itself, so that no data is consumed when it has no listeners.

Signal objects also behave like containers, in that they can be iterated
over (where each element is the :class:`~kaa.Callable` object), counted
(via ``len()``), and tested for membership (``myfunc in signal``).

A Signal knows how to be coerced into an :class:`~kaa.InProgress` object
via :func:`kaa.inprogress`, and can therefore be yielded from a :ref:`coroutine <coroutines>`::

    @kaa.coroutine()
    def stop_process(self):
        self.write('quit\n')
        # Let's assume the 'terminated' signal gets emitted when the process
        # exits, which is handled elsewhere.
        yield kaa.inprogress(self.signals['terminated'])
        
        # Once we get here, the 'terminated' signal was emitted.
        # [...]

Here, the ``stop_process()`` coroutine is finished when the ``terminated`` signal
is emitted.  For more information on coroutines, see the section on
:ref:`asynchronous programming in Kaa <coroutines>`.

A collection of many Signal objects is represented by a :class:`~kaa.Signals`
object, which behaves like a dictionary.  There are several additional methods
with Signals object, such as :meth:`~kaa.Signals.any` and :meth:`~kaa.Signals.all`.


Signals API
~~~~~~~~~~~

.. kaaclass:: kaa.Signal
   :synopsis:

   .. automethods::
   .. autoproperties::
   .. autosignals::


.. kaaclass:: kaa.Signals
   :synopsis:

   .. automethods::
   .. autoproperties::
   .. autosignals::
