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

Your distribution might already have kaa.base included in its standard
repositories, but be aware that these are almost certainly very out of date:

.. code-block:: bash

    # For Ubuntu and Debian
    sudo apt-get install python-kaa-base

    # For Fedora
    yum install python-kaa-base


The most recent in-development version can be obtained via subversion:

.. code-block:: bash

    svn co svn://svn.freevo.org/kaa/trunk/base kaa-base
    cd kaa-base
    sudo python setup.py install


Finally, source packages are `available on SourceForge
<http://sourceforge.net/projects/freevo/files/kaa-base/>`_.



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
