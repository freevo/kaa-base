The Kaa Application Framework
=============================


What are Kaa and kaa.base?
--------------------------

Kaa is an umbrella project comprising a set of Python modules, mostly inclined
toward solving problems in the domain of multimedia.

*kaa.base* is an LGPL-licensed generic Python application framework, providing
the foundation for other modules within Kaa, and can be used in any type of
project, from small event-driven tools, to larger, complex applications.

The Kaa Application Framework includes a :ref:`main loop facility <notifier>`
with an API for :ref:`signals <signals>` and :ref:`callables <callables>`,
:ref:`timers <timer>`, :ref:`thread <threads>` and :ref:`subprocess management
<subprocess>`, local :ref:`IO <io>` and :ref:`sockets <socket>` (with TLS
support), inter-process communication, and much more.

Kaa also -- and perhaps most importantly -- provides a rich, practically
magical API for :ref:`asynchronous programming <coroutines>`.  Threads and
coroutines in combination with :ref:`InProgress <inprogress>` objects,
which are used extensively throughout Kaa, allow you to implement complex state
machines responding to asynchronous events in very compact, readable code.

Here is a small taste of what an application written using Kaa looks like::

    import time, socket, errno
    import kaa

    @kaa.timed(1)
    def timer():
        "This function is invoked every second from the main loop."
        print 'timer fired at', time.time()


    @kaa.threaded()
    def thread(count):
        "This function runs in a thread.  Notice it blocks."
        for i in range(count):
            print 'thread woke up at', time.time()
            time.sleep(1)


    @kaa.coroutine()
    def coroutine():
        "By yielding, this function can have multiple reentry points."
        # We can spawn a new instance of thread().  The coroutine will reenter
        # after thread() finishes, but the main loop is not blocked; the timer
        # we started keeps firing all the while.
        print 'coroutine starting'
        yield thread(3)

        # Sub-process IO doesn't block.
        stdout, stderr = yield kaa.Process('lsusb').communicate()

        # And of course sockets don't block. Notice that asynchronously
        # generated exceptions can be handled as if you were writing typical
        # blocking code.
        sock = kaa.Socket()
        try:
            yield sock.connect('www.freevo.org:80')
        except socket.error as e:
            print 'Connection failed:', e.strerror
        else:
            sock.write('GET / HTTP/1.0\n\n')
            webpage = yield sock.read()
            print webpage

        # We can yield back to the main loop at any time.
        yield kaa.NotFinished

        # Or we can be reentered after some (non-blocking) period of time.
        yield kaa.delay(2)

        # Ok, let's shut everything down.  Main loop stops and coroutine exits.
        kaa.main.stop()
        print 'coroutine done'

    # Start a new thread that runs thread() inside it.
    thread(10)
    # Start the timed function
    timer()
    # Invoke the coroutine.  It will immediately execute everything before the
    # first yield and then return, having scheduled itself for reentry.
    coroutine()
    # Start the main loop.  This blocks until explicitly stopped, or if
    # KeyboardInterrupt or SystemExit is raised, or if there is an uncaught
    # exception.
    kaa.main.run()


Where do I get kaa.base?
------------------------

The easiest and recommended way to install kaa.base is using *pip* (available
as the ``python-pip`` package in Ubuntu and Fedora):

.. code-block:: bash

    sudo pip install --upgrade kaa-base


Or, if you prefer to install kaa.base as an egg using *setuptools* (package
``python-setuptools`` on Ubuntu and Fedora):

.. code-block:: bash

    sudo easy_install -U kaa-base

The most up-to-date tree can be cloned with git:

.. code-block:: bash

    git clone git://github.com/freevo/kaa-base.git
    cd kaa-base
    sudo python setup.py install

The project is `hosted at GitHub <https://github.com/freevo/kaa-base>`_, so if
you'd like to contribute, you can can fork it and send pull requests.  

Your distribution might already have kaa.base included in its standard
repositories, but be aware that these are almost certainly very out of date:

.. code-block:: bash

    # For Ubuntu and Debian
    sudo apt-get install python-kaa-base

    # For Fedora
    yum install python-kaa-base


Finally, source packages are `available on GitHub 
<https://github.com/freevo/kaa-base/downloads>`_.



Library Documentation
---------------------

Core Framework
~~~~~~~~~~~~~~

.. toctree::
   :maxdepth: 1
   :glob:

   core/signals
   core/mainloop
   core/timer
   core/event
   async/inprogress
   async/coroutines
   async/threads
   async/generators
   core/io
   core/socket
   core/process


Utility Modules
~~~~~~~~~~~~~~~

.. toctree::
   :maxdepth: 1
   :glob:

   rpc
   config
   db
   inotify
   utils
   input


Network
~~~~~~~

.. toctree::
   :maxdepth: 2

   net/tls
   net/mdns


Miscellaneous
~~~~~~~~~~~~~

.. toctree::
   :maxdepth: 2

   distribution
   internal/index
