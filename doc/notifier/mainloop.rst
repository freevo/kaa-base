Main loop
=========

Overview
--------

The main loop facility within kaa is based on pyNotifier. A
system-wide installation of pynotifier will be used if it exists,
otherwise kaa will fallback to an internal version which supports
integration with gtk and twisted main loops. kaa.base fully wraps and
enhances stock pyNotifier API with process, thread and signal handling
and a wide variety of callback classes.

To start the main loop, you need to import kaa and call
kaa.main.run(). When the program stops because you press Ctrl-c in the
terminal, send a SIG15 or call sys.exit, the application won't
stop. It will just terminate the main loop (i.e. kaa.main.run()
returns)::

    import kaa
    kaa.main.run()

This is a trivial example of course; your program should do
something. The other classes available in kaa.base (described below)
can be used to hook functionality into the main loop. As a general
rule, one should try not to block the main loop for longer than 100
milliseconds. kaa.base provides several options to avoid blocking,
such as coroutines or threads. See SourceDoc/Async for further
discussion of asynchronous programming with Kaa.

The notion of signals is used heavily within all kaa modules. Here,
signals are similar to gtk signals, in that they are hooks to allow
you to connect callbacks when certain events occur. There is a
dictionary signals called kaa.main.signals which contains several
signals to which you can connect. In some cases, this dictionary is
extended when modules are imported.

Depending on what you currently use, some small steps need to be made
to make the notifier loop running. If you aren't using a main loop
right now, you should use the kaa main loop.

GTK
---

The generic notifier is compatible with the GTK/Glib mainloop and kaa
notifier has a special handler to hook itself into the GTK/Glib
mainloop. Kaa notifier will use the GTK/Glib mainloop when gtk or
gobject is imported once the mainloop is active. But it is possible to
force the notifier loop to use GTK/Glib by calling init::

    import kaa.notifier
    kaa.notifier.init('gtk')

This will the the GTK mainloop (the GTK mainloop is based on the glib
mainloop but is a bit different). If you want the glib and not the GTK
based mainloop add x11 = False to init.

If pyNotifier is installed it will be used to run the mainloop; usage
of packages requiring pyNotifier and not kaa.notifier is possible.

Twisted
-------

Kaa.notifier defines a Twisted reactor to integrate the Twisted
mainloop into the kaa mainloop. After installing the reactor you can
either run kaa.main() or reactor.run() to start the mainloop. Due to
the internal design of Twisted you can not stop the mainloop from
Twisted callbacks by calling sys.exit() or kaa.notifier.shutdown(),
you need to call reactor.stop(). From kaa callbacks sys.exit() and
kaa.notifier.stop() is supported::

    # install special kaa reactor
    import kaa.notifier.reactor
    kaa.notifier.reactor.install()
    
    # get reactor
    from twisted.internet import reactor
    
    # add callbacks to Twisted or kaa.notifier
    # see test/twisted_in_kaa.py in the kaa.base package
    
    # you can either call kaa.main() or reactor.run()
    kaa.main()

The Twisted reactor will work with any kaa.notifier backend (generic
and gtk).

There is also the reverse option putting the kaa mainloop into Twisted
and let the Twisted reactor run. This is based on the thread notifier
described below and will not use an external pyNotifier installation::

    # get reactor
    from twisted.internet import reactor
    
    import kaa.notifier
    kaa.notifier.init('twisted')
    
    # add callbacks to Twisted or kaa.notifier
    # see test/kaa_in_twisted.py in the kaa.base package
    
    # run Twisted mainloop
    reactor.run()

Other mainloops
---------------

PyNotifier has wrappers for qt and wxwindows but they may not work as
expected with other kaa modules. For that reasons they can not be
selected. It is always possible to run the kaa.notifier mainloop in a
thread but that also means that kaa modules and other parts of the
code have a different idea what the mainloop is.

A different solution is the thread based notifier in kaa.notifier. In
this mode the kaa mainloop will run in an extra thread and will call a
callback to the real mainloop that should be called from the real main
thead. The other mainloop only needs to support a callback function
that will be called from a thread and will execute the argument (a
function without parameter) from the mainloop. An extra argument can
be provided for a clean shutdown if the kaa mainloop whats to shut
down the system. If not callback is provided, kaa.notifier.shutdown
will be called.

The following example will integrate the kaa mainloop in the normal
Twisted reactor. In this case the Twisted mainloop is running,
kaa.main() should not be called::

    # get reactor
    from twisted.internet import reactor
    
    # start thread based mainloop and add Twisted callback
    import kaa.notifier
    kaa.notifier.init('thread', handler = reactor.callFromThread, 
                      shutdown = reactor.stop)
    
    # add callbacks to Twisted or kaa.notifier
    # see test/kaa_in_twisted.py in the kaa.base package
    
    # run Twisted mainloop
    reactor.run()

Note: the notifier step signal will only be called every step the kaa
mainloop does and does not affect steps the real mainloop does. Future
version of kaa.notifier may fix that problem.

If you create a wrapper to use kaa.notifier with a different notifier
using this solution please send us an example so we can include
support for that mainloop in the kaa distribution.
