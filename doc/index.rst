kaa.base --- The Kaa Application Framework
==========================================

What are Kaa and kaa.base?
--------------------------

Kaa is an umbrella project comprising a set of Python modules, mostly inclined
toward solving problems in the domain of multimedia.

*kaa.base* is an LGPL-licensed generic application framework, providing the
foundation for other modules within Kaa, and can be used in any type of
project, from small event-driven tools, to larger, complex applications.

The Kaa Application Framework includes a :ref:`main loop facility <notifier>`
with an API for :ref:`signals <signals>` and :ref:`callables <callables>`,
:ref:`timers <timer>`, :ref:`thread <threads>` and :ref:`subprocess management
<subprocess>`, local :ref:`IO <io>` and :ref:`sockets <socket>` (with TLS
support), inter-process communication, and much more.

Kaa also -- and perhaps most importantly -- provides a rich, practically
magical API for :ref:`asynchronous programming <async>`.  Threads and
coroutines in combination with :ref:`InProgress <inprogress>` objects,
which are used extensively throughout Kaa, allow you to implement complex state
machines responding to asynchronous events in very compact, readable code.

Where do I get kaa.base?
------------------------

Source packages are `available on SourceForge
<https://sourceforge.net/project/showfiles.php?group_id=46652&package_id=213183>`_.

Your distribution might already have *kaa.base* included in its standard
repositories::

    # For Ubuntu and Debian
    sudo apt-get install python-kaa-base

    # For Fedora
    yum install python-kaa-base


If you have *setuptools* installed (package named ``python-setuptools`` on
Ubuntu and Fedora), you can install (or upgrade to) the latest released
version, which will very likely be more recent than the version that comes
with your distribution::

    sudo easy_install -U kaa-base


The most recent in-development version can be obtained via subversion::

    svn co svn://svn.freevo.org/kaa/trunk/base kaa-base


Framework Documentation
-----------------------

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
