.. module:: kaa.timer
   :synopsis: Invoke callbacks at specified intervals or times of day
.. _timer:

Timers
======

The timed decorator
-------------------

FIXME: this section is not yet written

.. autofunction:: kaa.timed(interval, timer=None, policy=POLICY_MANY)


Timer Callbacks
---------------

FIXME: this section is not yet written

.. kaaclass:: kaa.Timer
   :synopsis:

   .. automethods::
      :remove: unregister
   .. autoproperties::
   .. autosignals::

.. kaaclass:: kaa.WeakTimer
   :synopsis:
   
.. kaaclass:: kaa.OneShotTimer
   :synopsis:

.. kaaclass:: kaa.WeakOneShotTimer
   :synopsis:

.. kaaclass:: kaa.OneShotAtTimer
   :synopsis:

   .. automethods::
      :remove: start

      .. automethod:: start(hour=range(24), min=range(60), sec=0)

.. kaaclass:: kaa.AtTimer
   :synopsis:
