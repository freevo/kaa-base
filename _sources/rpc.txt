.. module:: kaa.rpc
   :synopsis: Inter-process communication through Remote Procedure Calls 

Remote Procedure Calls with kaa.rpc
===================================

This module defines an alternative way for InterProcessCommunication
with less features than the ipc.py module. It does not keep
references, return values are only given back as a callback and it is
only possible to access functions. The difference between client and
server is only important on connect. Both can call functions for the
other.

Start a server::

    kaa.rpc.Server(address, secret)

When a new client connects to the server, the 'client_connected'
signals will be emitted with a Channel object as parameter. This
object can be used to call functions on client side the same way the
client calls functions on server side. The client and the channel
objects have a signal 'disconnected' to be called when the connection
gets lost.

Start a client::

    kaa.rpc.Client(address, secret)

Since everything is async, the challenge response is done in the background
and you can start using it right away. If the authentication is wrong, it
will fail without notifing the user (I know this is bad, but it is designed
to work internaly where everything is correct).

.. kaaclass:: kaa.rpc.Server
   :synopsis:

   .. automethods::
   .. autoproperties::
   .. autosignals::


.. kaaclass:: kaa.rpc.Client
   :synopsis:

   .. automethods::
      :inherit:
   .. autoproperties::
      :inherit:
   .. autosignals::
      :inherit:


Expose Functions
----------------

Next you need to define functions the remote side is allowed to call
and give it a name. Use use expose for that. Connect the object with
that function to the server/client. You can connect as many objects as
you want. The client can now call do_something (not my_function, this
is the internal name). If the internal name should be exposed the
expose decorator does not need its first argument::

    class MyClass(object)

        @kaa.rpc.expose("do_something")
        def my_function(self, foo):
            ...

        @kaa.rpc.expose()
        def name(self, foo):
            ...

    server.connect(MyClass())

.. autofunction:: kaa.rpc.expose

Calling Remote Functions
------------------------

A remote function call be called with the rpc method in the client or
the server. The result is an InProgress object. Connect to it to get
the result::

    x = client.rpc('do_something', 6) or
    x = client.rpc('do_something', foo=4)

Using Python 2.5 and coroutines the asynchronous call can be wrapped
in a yield statement, hiding the delay of the RPC. If the server
raises an exception, it will be raised on client side. This makes
remote functions look like local functions. Note: Python will jump
back to the mainloop in each yield::

    @kaa.coroutine()
    def foo():
        name = yield client.rpc('name')
        print name
