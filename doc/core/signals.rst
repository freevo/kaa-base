Signals and Callbacks
=====================

Signal and Callback objects are among the core building blocks of the Kaa framework
and are used extensively throughout.


Callbacks
---------

Callback objects encapsulate a callable (such as a function or method) and, optionally,
any number of arguments and keyword arguments.  Callback objects are in turn callable,
and upon invocation will call the underlying callable, passing it all arguments passed
on invocation and all arguments passed to the constructor.  As the name suggests,
the main use-case of Callback objects is any time a callback function is required,
such as with signals (described later).

Callbacks can be used to construct partial functions::

    >>> square = kaa.Callback(pow, 2)
    >>> print square(5)
    25

(Of course this example is a bit contrived, because you could use lambda to
achieve the same result with less overhead.  But it helps to start simple.)

By default, all arguments passed upon invocation of the Callback are passed to the
underlying callable first, followed by arguments passed upon construction.  So the
above example translates to ``pow(5, 2)``.  It is possible to reverse this behaviour
by setting the :attr:`~kaa.Callback.user_args_first` property to True::

    >>> square.user_args_first = True
    >>> square(5)  # Of course, now this isn't a square
    32

Keyword arguments work in a similar way.  Keyword arguments passed to both
the constructor and upon invocation are passed to the callable.
When ``user_args_first`` is ``False`` (default), keyword arguments passed on
invocation take precedence (overwrite) same-named keyword arguments passed on
the constructor.  When ``True``, keyword arguments from the constructor take
precedence over those passed upon invocation.

Here's an example that more clearly demonstrates the rules of precedence::

    >>> def func(*args, **kwargs):
    ...     print 'Callback:', args, kwargs
    ... 
    >>> cb = kaa.Callback(func, 1, 2, foo=42, bar='kaa')
    >>> cb()
    Callback: (1, 2) {'foo': 42, 'bar': 'kaa'}
    >>> cb('hello world', foo='overrides', another='kwarg')
    Callback: ('hello world', 1, 2) {'foo': 'overrides', 'bar': 'kaa', 'another': 'kwarg'}
    >>> cb.user_args_first = True
    >>> cb('hello world', foo="doesn't override", another='kwarg')
    Callback: (1, 2, 'hello world') {'foo': 42, 'bar': 'kaa', 'another': 'kwarg'}


Because Callback objects hold references to the callable (or more specifically,
the instance if the callable is a method) and any arguments passed at construction
time, those objects remain alive as long as the Callback is referenced.  This is
not always what's wanted, and in those cases the :class:`~kaa.WeakCallback` variant
can be used.

With :class:`~kaa.WeakCallback`, only weak references are held to the callable
and constructor arguments.  When any of the underlying objects are destroyed,
the WeakCallback ceases to be valid.  One common use-case for WeakCallback
is to avoid cyclical references.  For example, an object may hold an
:class:`~kaa.IOMonitor` on some file descriptor, and have a method invoked
when there's activity.  Consider this example::

    class MyClass(object):
        def __init__(self, fd):
            self._monitor = kaa.IOMonitor(self._handle_read)
            self._monitor.register(fd)

In this example, a reference cycle is created: the MyClass instance holds
a reference to the IOMonitor, which holds a reference to the _handle_read method
of the MyClass instance (which implicitly holds a reference to the MyClass instance
itself).

You might be thinking this isn't a problem: after all, Python has a garbage collector
that will detect and break orphaned cyclic references.  However, because the fd is
registered (with the notifier), Kaa keeps an internal reference to the IOMonitor.
Therefore, even if all user-visible references to the MyClass instance are gone,
neither that object nor the IOMonitor ever get deleted (at least so long as the
fd is open).

If you want the IOMonitor to automatically become unregistered when the callback
(or specifically the instance the method belongs to) is destroyed, you can use a
WeakCallback::

    self._monitor = kaa.IOMonitor(kaa.WeakCallback(self._handle_read))

In this example, when the notifier would normally invoke the callback (when
there is activity on the registered file descriptor), it will find the
callback is in fact dead and automatically unregister the monitor.  With this,
the instance of MyClass is allowed to be destroyed  (at least insofar as Kaa
would not hold any internal references to it).

Now, the previous example is a bit clumsy because it requires the callback
to be invoked (or attempted to be) before the monitor is automatically 
unregistered.  It would be cleaner if the monitor was registered immediately
when the MyClass instance is destroyed.  For this, the weak variant of IOMonitor
called WeakIOMonitor can be used::

    self._monitor = kaa.WeakIOMonitor(self._handle_read)

Weak variants of these notifier-aware classes exist throughout Kaa: WeakIOMonitor,
WeakTimer, WeakOneShotTimer, WeakEventHandler.



Callback API
~~~~~~~~~~~~

.. kaaclass:: kaa.Callback

   .. automethods::
      :add: __call__

   .. autoproperties::


.. kaaclass:: kaa.WeakCallback

   .. autoproperties::


Signals
-------

FIXME: add overview and example of a typical way to use signals


.. kaaclass:: kaa.Signal

   .. automethods::
   .. autoproperties::
   .. autosignals::


.. kaaclass:: kaa.Signals

   .. automethods::
   .. autoproperties::
   .. autosignals::


Connect-Change Notification
---------------------------

FIXME: this section is not yet written
