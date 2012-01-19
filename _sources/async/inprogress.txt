.. module:: kaa.async
   :synopsis: InProgress objects: the foundation to all asynchronous tasks in Kaa
.. _inprogress:


InProgress Objects
==================

Throughout Kaa, when a function executes asynchronously (which is generally the
case for any function that may otherwise block on some resource), it returns an
InProgress object. The InProgress object is a :class:`~kaa.Signal` that
callbacks can be connected to in order to handle its return value or any
exception raised during the asynchronous execution. When the InProgress object
is emitted, we say that it is "finished" (and the
:attr:`~kaa.InProgress.finished` property is True).

InProgress objects are emitted (they are :class:`~kaa.Signal` objects,
remember) when finished, so handlers can retrieve the return value of the
asynchronous task. There is also an :attr:`~kaa.InProgress.exception` member,
which is itself a Signal, and is emitted when the asynchronous task raises an
exception. Exception handlers must accept three arguments: exception class,
exception instance, and traceback object.  (These three arguments correspond to
sys.exc_info())

The following example demonstrates how one might connect callbacks to an InProgress
in order to handle success result and exceptions::

    import kaa

    def handle_connect(result):
        print 'Connected to remote site successfully'

    def handle_exception(tp, exc, tb):
        print 'Connect failed:', exc
        
    sock = kaa.Socket()
    inprogress = sock.connect('www.freevo.org:80')
    inprogress.connect(handle_connect)
    inprogress.exception.connect(handle_exception)
    # Or a convenience function exists to replace the above 2 lines:
    # inprogress.connect_both(handle_connect, handle_exception)
    kaa.main.run()


Connecting callbacks to signals in this way is fairly standard and this
approach is used in many other frameworks.  For example, readers familiar
with the Twisted framework may find similarities with Twisted's Deferreds.

However, InProgress objects can be used with :ref:`coroutines <coroutines>`
(covered in more detail later), a more interesting and powerful approach which
allows you to handle the result of InProgress objects without the use of
callbacks.  The above example could be rewritten as::

    import kaa
    
    @kaa.coroutine()
    def connect(site):
        sock = kaa.Socket()
        try:
            yield sock.connect(site)
        except Exception, exc:
            print 'Connect failed:', exc
        else:
            print 'Connected to remote site successfully'

    connect('www.freevo.org:80')
    kaa.main.run()

As seen in the above snippet, with coroutines, InProgress objects are used
implicitly, where they function as a mechanism for message passing between
asynchronous tasks and the coroutine machinery built into the :ref:`notifier
<notifier>`.

If an InProgress finishes with an exception (in which case the
:attr:`~kaa.InProgress.failed` property is True) but it is not handled
by one of the above methods (either by connecting a callback to the
*exception* attribute, or by catching the exception raised by a yield
in a coroutine), the exception will be logged to stderr with the heading
"Unhandled asynchronous exception."


.. kaaclass:: kaa.InProgress
   :synopsis:

   .. automethods::
      :order: abort, connect, connect_both, execute, finish, throw, timeout, wait, waitfor
      :remove: Progress, is_finished, get_result

      .. method:: connect(callback, \*args, \*\*kwargs)

         Connects a callback to be invoked when the InProgress has
         returned normally (no exception raised).

         If the asynchronous task raises an exception, the InProgress
         finishes with that exception and the :attr:`~kaa.InProgress.exception`
         signal is emitted.

   .. autoproperties::
   .. autosignals::



InProgress Collections
----------------------

.. kaaclass:: kaa.InProgressAny

.. kaaclass:: kaa.InProgressAll


InProgress Exceptions
---------------------

The following exceptions can be raised by InProgress methods.

.. kaaclass:: kaa.TimeoutException

.. kaaclass:: kaa.InProgressAborted


Functions
---------

.. autofunction:: kaa.inprogress

   A practical demonstration of this protocol is in the Signal object,
   which implements the __inprogress__ method. The returned InProgress in
   that case is finished when the signal is next emitted. Any object
   implementing the __inprogress__ protocol can be passed directly to the
   constructor of InProgressAny or InProgressAll.

.. autofunction:: kaa.delay
