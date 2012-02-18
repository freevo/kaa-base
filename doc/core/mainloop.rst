.. module:: kaa.main
   :synopsis: The main loop facility

The Main Loop
=============

.. _notifier:

The plumbing within Kaa that orchestrates the main loop -- dispatching
callbacks triggered by events (such as activity on a file descriptor or timers)
-- is collectively referred to as "*the notifier*."  If you're familiar with the
Twisted framework, it is very similar to Twisted's reactor.

This main loop facility depends on pyNotifier. A system-wide installation of
pynotifier will be used if it exists, otherwise kaa will fallback to an
internal version which supports integration with gtk and Twisted main loops.
kaa.base fully wraps and enhances stock pyNotifier API with process, thread and
signal handling and a wide variety of classes suitable for constructing
callables used as callbacks.

To start the main loop, import kaa and call :func:`kaa.main.run`.  The main
loop (but *not* the program) will terminate when SIGTERM or SIGINT (ctrl-c) is
received.  The simplest Kaa program is therefore::

    import kaa
    kaa.main.run()

This program is effectively deaf and mute.  Internally, it will go to sleep for
30 seconds, wake up briefly, sleep again, and so on.  (30 is a happenstance of
the internal pyNotifier implementation; 30 seconds is basically infinity as far
as a computer is concerned.)

From the above basic shell, you can begin hooking functionality into the
program via the rest of the Kaa API: :ref:`timers <timer>`, :ref:`sockets
<socket>`, :ref:`subprocesses <subprocess>`, :ref:`I/O channels <io>`,
:ref:`coroutines <coroutines>`, :ref:`threads <threads>`, etc.


Main Loop API
-------------

.. autofunction:: kaa.main.run

.. autofunction:: kaa.main.stop

.. autofunction:: kaa.main.loop

.. autofunction:: kaa.main.is_running

.. autofunction:: kaa.main.is_shutting_down

.. autofunction:: kaa.main.is_stopped

.. autofunction:: kaa.main.step

.. autofunction:: kaa.main.init



Main Loop Signals
-----------------

.. _mainsignals:

Global Kaa signals are accessed via the ``kaa.signals`` :class:`~kaa.Signals` object.
For example::

    def shutdown_handler():
        print 'Shutting down'

    kaa.signals['shutdown'].connect(shutdown_handler)


Importing other Kaa modules (such as those in :mod:`kaa.input`) may add specialized
signals, however by default ``kaa.signals`` contains:

.. attribute:: shutdown

   Emitted when the Kaa main loop is shutting down, but before any
   subprocesses or threads are terminated.

   .. describe:: def callback()

      The callback takes no arguments.

.. attribute:: exit

   Emitted when the process exits.  This differs from the ``shutdown`` signal
   in that the Python program may continue to run after ``shutdown`` emits and
   the mainloop terminates, whereas ``exit`` is invoked from an ``atexit``
   handler.

   .. describe:: def callback()

      The callback takes no arguments.

.. attribute:: step

   Emitted after each iteration step of the main loop.

   This signal is probably not suitable as an 'idle worker' because the
   interval between emissions may be as much as 30 seconds.  However it is
   useful for functions which need to be called after notifier callbacks
   such as timers and IO monitors.  One example use-case is rendering a
   canvas after notifier callbacks have manipulated objects upon it.

   .. describe:: def callback()

      The callback takes no arguments.

.. attribute:: exception

   Emitted when an uncaught exception has bubbled up to the main loop.  This
   signal presents the last chance to handle it before the main loop will
   be aborted.  (This also includes SystemExit and KeyboardInterrupt.)

   .. describe:: def callback(tp, exc, tb)

      The callback parameters correspond to sys.exc_info().

      :param tp: the exception class
      :param exc: the exception instance
      :param tb: the traceback for this exception

      If the callback returns ``False``, the exception will be considered
      handled and the main loop will *not* terminate.  Otherwise, it will.



Integration With Other Frameworks
=================================

Kaa can be made to play nicely with other main loop facilities.  For example,
you can write a pygtk application while still making use of Kaa's convenient
API.


GObject / GTK Integration
-------------------------

The generic mainloop is compatible with the GTK/Glib mainloop and kaa
has a special handler to hook itself into the GTK/Glib
mainloop. Kaa will use the GTK/Glib mainloop when gtk or
gobject is imported once the mainloop is active. But it is possible to
force the loop to use GTK/Glib by calling init::

    import kaa
    kaa.main.select_notifier('gtk')

This will the the GTK mainloop (the GTK mainloop is based on the glib
mainloop but is a bit different). If you want the glib and not the GTK
based mainloop add x11 = False to init.

If pyNotifier is installed it will be used to run the mainloop; usage
of packages requiring pyNotifier and not kaa is possible.

A different approuch is to use the generic mainloop and start the
gobject mainloop in a thread. This may be useful when one loop is
extremly timing depended and it is a bad idea to block for even a
short time. As an example, kaa.candy uses this to keep the gobject
loop small and the animations alive even when the real mainloop is
very busy.

.. autofunction:: kaa.gobject_set_threaded

Note that callbacks from the gobject mainloop are called in that loop
and not the kaa mainloop. Make sure you decorate the mainloop with the
threaded decorator if necessary. For details about thread support see
:ref:`threads`. The `threaded` decorator can be used to force
execution of a function in the gobject mainloop. Use `kaa.GOBJECT` as
thread name::

  import kaa

  @kaa.threaded(kaa.MAINTHREAD)
  def executed_in_kaa_mainloop():
      ...

  @kaa.threaded(kaa.GOBJECT)
  def executed_in_gobject_mainloop():
      ...

  kaa.main.select_notifier('generic')
  kaa.gobject_set_threaded()
  kaa.main.run()


Twisted Integration
-------------------

Kaa defines a Twisted reactor to integrate the Twisted
mainloop into the kaa mainloop. After installing the reactor you can
either run kaa.main.run() or reactor.run() to start the mainloop. Due
to the internal design of Twisted you can not stop the mainloop from
Twisted callbacks by calling sys.exit() or kaa.main.shutdown(), you
need to call reactor.stop(). From kaa callbacks sys.exit() and
kaa.main.stop() is supported::

    # install special kaa reactor
    import kaa.reactor
    kaa.reactor.install()

    # get reactor
    from twisted.internet import reactor

    # add callbacks to Twisted or kaa
    # see test/twisted_in_kaa.py in the kaa.base package

    # you can either call kaa.main.run() or reactor.run()
    kaa.main.run()

The Twisted reactor will work with any kaa mainloop backend (generic
and gtk).

There is also the reverse option putting the kaa mainloop into Twisted
and let the Twisted reactor run. This is based on the thread mainloop
described below and will not use an external pyNotifier installation::

    # get reactor
    from twisted.internet import reactor

    import kaa
    kaa.main.select_notifier('twisted')

    # add callbacks to Twisted or kaa
    # see test/kaa_in_twisted.py in the kaa.base package

    # run Twisted mainloop
    reactor.run()


Other mainloops
---------------

PyNotifier has wrappers for qt and wxwindows but they may not work as
expected with other kaa modules. For that reasons they can not be
selected. It is always possible to run the kaa mainloop in a
thread but that also means that kaa modules and other parts of the
code have a different idea what the mainloop is.

A different solution is the thread based mainloop in kaa. In
this mode the kaa mainloop will run in an extra thread and will call a
callback to the real mainloop that should be called from the real main
thead. The other mainloop only needs to support a callback function
that will be called from a thread and will execute the argument (a
function without parameter) from the mainloop. An extra argument can
be provided for a clean shutdown if the kaa mainloop whats to shut
down the system. If not callback is provided, kaa.main.shutdown
will be called.

The following example will integrate the kaa mainloop in the normal
Twisted reactor. In this case the Twisted mainloop is running,
kaa.main.run() should not be called::

    # get reactor
    from twisted.internet import reactor

    # start thread based mainloop and add Twisted callback
    import kaa
    kaa.main.select_notifier('thread', handler = reactor.callFromThread,
                             shutdown = reactor.stop)

    # add callbacks to Twisted or kaa
    # see test/kaa_in_twisted.py in the kaa.base package

    # run Twisted mainloop
    reactor.run()

Note: the step signal will only be called every step the kaa
mainloop does and does not affect steps the real mainloop does. Future
version of kaa may fix that problem.

If you create a wrapper to use kaa with a different mainloop
using this solution please send us an example so we can include
support for that mainloop in the kaa distribution.
