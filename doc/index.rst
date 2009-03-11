kaa.base --- The Kaa Application Framework
==========================================

Kaa is an umbrella project comprising a set of Python modules, mostly inclined
toward solving problems in the domain of multimedia.

kaa.base is an LGPL-licensed generic application framework, providing the
foundation for other modules within Kaa, and can be used in any type of
project, from small event-driven tools, to larger, complex applications.

The Kaa Application Framework includes a mainloop facility with an API for
signals and callbacks, timers, thread and subprocess management, local IO and
sockets (with TLS support), and inter-process communication.

Kaa also -- and perhaps most importantly -- provides a rich, practically
magical API for asynchronous programming.  Threads and coroutines in
combination with :class:`~kaa.InProgress` objects, which are used extensively
throughout Kaa, allow you to implement complex state machines responding
to asynchronous events in very compact, readable code.

Contents:

.. toctree::
   :maxdepth: 2

   core/index
   async/index
   rpc


TODO: kaa.config, kaa.db, kaa.distribution, kaa.input,
kaa.ioctl, kaa.net.mdns, kaa.net.tls, kaa.net.url, kaa.strutils,
kaa.utils, kaa.weakref, kaa.xmlutils. The logger manipulation in
kaa.logger should also be documented as automatic function. Also
missing are the extensions for inotify and shm, kaa.signals,
kaa.Event, and kaa.Eventhandler

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
