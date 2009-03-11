.. kaa.base documentation master file, created by sphinx-quickstart
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

kaa.base documentation
======================

This module provides the base Kaa framework and is an implicit
dependency for all kaa modules. The kaa framework includes a mainloop
facility with an API for signals and callbacks, timers, process and
thread management, file descriptor monitoring (with INotify support),
inter-process communication, as well as a rich, practically magical
API for asynchronous programming.

Some of the sub-modules in kaa.base have dependencies (such as kaa.db,
which requires pysqlite and glib), and while these dependencies are
required for those sub-modules, kaa.base itself does not require those
sub-modules. Some of the other modules in Kaa may require these
sub-modules, and in the case where the sub-modules have optional
dependencies in kaa.base (see below), they will be explicitly listed
as dependencies in the other modules. For example, kaa.epg requires
both kaa.db and kaa.rpc, but only kaa.db will be listed as a
dependency for kaa.epg because only it is optional within kaa.base.

Contents:

.. toctree::

   core/index
   async/index
   rpc

But that is not all. The following parts of kaa.base need to be
documented: kaa.config, kaa.db, kaa.distribution, kaa.input,
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
