.. _timer:

Timer
=====

The timed decorator
-------------------

FIXME: this section is not yet written

.. autofunction:: kaa.timed(interval, timer=None, policy=POLICY_MANY)


Timer Callbacks
---------------

FIXME: this section is not yet written

.. kaaclass:: kaa.Timer

   .. automethods::
      :remove: unregister
   .. autoproperties::
   .. autosignals::

.. kaaclass:: kaa.WeakTimer
    
.. kaaclass:: kaa.OneShotTimer

.. kaaclass:: kaa.WeakOneShotTimer

.. kaaclass:: kaa.OneShotAtTimer

   .. automethods::
      :remove: start

      .. automethod:: start(hour=range(24), min=range(60), sec=0)

.. kaaclass:: kaa.AtTimer
