.. _async:

Asynchronous Programming
========================

One of the design goals of kaa is to provide a suitable framework that can be
used to avoid blocking the main loop for extended periods (in order to improve
interactivity and reduce latency), and kaa.base provides two convenient
approaches to accomplish this with asynchronous programming -- :ref:`coroutines
<coroutines>` and :ref:`threads <threads>` -- which are unified through
:ref:`InProgress <inprogress>` objects.

Contents:

.. toctree::
   :maxdepth: 2

   inprogress
   coroutines
   threads
   generators
