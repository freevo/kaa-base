.. module:: kaa.strutils
   :synopsis: String utility functions

Utility Functions
=================

String
------

The following two functions (py3_str() and py3_b()) are commonly used utility functions,
and so they are exposed directly in the kaa namespace.

.. autofunction:: kaa.py3_str
.. autofunction:: kaa.py3_b
.. autofunction:: kaa.strutils.nativestr
.. autofunction:: kaa.strutils.fsname
.. autofunction:: kaa.strutils.utf8
.. autofunction:: kaa.strutils.get_encoding
.. autofunction:: kaa.strutils.set_encoding
.. autofunction:: kaa.strutils.format
.. attribute:: kaa.strutils.BYTES_TYPE
.. attribute:: kaa.strutils.UNICODE_TYPE


.. module:: kaa.utils
   :synopsis: Miscellaneous useful helper functions

Date and Time
-------------

TODO: utc, local


Miscellaneous
-------------

TODO: property

.. autofunction:: kaa.utils.tempfile
.. autofunction:: kaa.utils.which
.. autofunction:: kaa.utils.fork
.. autofunction:: kaa.utils.daemonize
.. autofunction:: kaa.utils.is_running
.. autofunction:: kaa.utils.set_running
.. autofunction:: kaa.utils.set_process_name
.. autofunction:: kaa.utils.get_num_cpus
.. autofunction:: kaa.utils.get_machine_uuid
.. autofunction:: kaa.utils.get_plugins
.. autofunction:: kaa.utils.wraps
.. autoclass:: kaa.utils.DecoratorDataStore
.. autofunction:: kaa.utils.weakref


IOCTL
-----

The *kaa.ioctl* module provides functions for the C-level ioctl macros that are
defined in ``/usr/include/asm-generic/ioctl.h`` used for creating and decoding
ioctl numbers.

.. autofunction:: kaa.ioctl.IO
.. autofunction:: kaa.ioctl.IOR
.. autofunction:: kaa.ioctl.IOR
.. autofunction:: kaa.ioctl.IOWR
.. autofunction:: kaa.ioctl.IOC_DIR
.. autofunction:: kaa.ioctl.IOC_TYPE
.. autofunction:: kaa.ioctl.IOC_NR
.. autofunction:: kaa.ioctl.IOC_SIZE
.. autofunction:: kaa.ioctl.ioctl
