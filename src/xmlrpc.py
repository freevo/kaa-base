# -* -coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# xmlrpc.py - Simple XMLRPC handling
# -----------------------------------------------------------------------------
# $Id$
#
# This module defines a basic XMLRPC client and server. The interface is
# more or less identical to the one from rpc.py with the following
# exceptions:
# 1. It uses XMLRPC over HTTP which is a standard for IPC
# 2. It is less secure but it should not matter in a LAN
# 3. It is slower because it creates a new connection on every request
# 4. It is unidirectional, the server can not call the client
# 5. Names arguments are now allowed (not supported by libxmlrpc)
#
# Documentation:
#
# Start a server: kaa.rpc.Server(address, secret)
# Start a client: kaa.rpc.Client(address, secret)
#
# If secret is given basic HTTP authentication with realm and user xmlrpc
# is used. The password is the given secret. Everything is async and threads
# are used to avoid blocking (this should be fixed some day). The callbacks
# are handled in the mainloop, the threads are only internal.
#
# You need to define functions the remote side is allowed to call and
# give it a name. Use use expose for that.
#
# | class MyClass(object)
# |   @kaa.rpc.expose("do_something")
# |   def my_function(self, foo)
#
# Connect the object with that function to the server/client. You can connect
# as many objects as you want
# | server.connect(MyClass())
#
# The client can now call do_something (not my_function, this is the internal
# name). To do that, you need to create a RPC object with the callback you
# want to have
#
# | x = client.rpc('do_something', 6) or
#
# The result is an InProgress object. Connect to it to get the result.
#
# -----------------------------------------------------------------------------
# Copyright (C) 2007 Dirk Meyer, Jason Tackaberry
#
# First Edition: Dirk Meyer <dischi@freevo.org>
# Maintainer:    Dirk Meyer <dischi@freevo.org>
#
# Please see the file AUTHORS for a complete list of authors.
#
# This library is free software; you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License version
# 2.1 as published by the Free Software Foundation.
#
# This library is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301 USA
#
# -----------------------------------------------------------------------------

__all__ = [ 'Server', 'Client', 'expose' ]

# python imports
import types
import base64
import xmlrpclib
from SimpleXMLRPCServer import SimpleXMLRPCServer, SimpleXMLRPCRequestHandler

# kaa imports
import kaa.notifier

def expose(command):
    """
    Decorator to expose a function.
    """
    def decorator(func):
        func._kaa_xmlrpc = command
        return func
    return decorator


class AuthenticatedHTTPRequestHandler(SimpleXMLRPCRequestHandler):
    """
    SimpleXMLRPCRequestHandler with HTTP authentication.
    """
    def do_POST(self):
        if self.server.auth and self.headers.get('authorization') != self.server.auth:
            self.send_response(401)
            self.send_header('WWW-Authenticate', 'Basic realm="xmlrpc"')
            self.end_headers()
        else:
            SimpleXMLRPCRequestHandler.do_POST(self)


class Server(SimpleXMLRPCServer):
    """
    XMLRPC server class.
    """

    allow_reuse_address = True

    def __init__(self, address, auth_secret=''):
        SimpleXMLRPCServer.__init__(self, address, AuthenticatedHTTPRequestHandler, 0)
        kaa.notifier.WeakSocketDispatcher(self._handle_request).register(self.fileno())
        kaa.signals['shutdown'].connect_weak(self.server_close)
        self.auth = None
        if auth_secret:
            self.auth = 'Basic ' + base64.encodestring('xmlrpc:%s' % auth_secret)[:-1]


    def _handle_request(self):
        """
        Internal class to use threads for request handling.
        """
        kaa.notifier.Thread(self.handle_request).start()


    def connect(self, obj):
        """
        Connect an object to be exposed.
        """
        if type(obj) == types.FunctionType:
            callables = [obj]
        else:
            callables = [ getattr(obj, func) for func in dir(obj) ]

        for func in callables:
            if callable(func) and hasattr(func, '_kaa_xmlrpc'):
                c = kaa.notifier.MainThreadCallback(func)
                c.set_async(False)
                self.register_function(c, func._kaa_xmlrpc)


class Client(object):
    """
    RPC client to be connected to a server.
    """
    def __init__(self, address, auth_secret=''):
        if auth_secret:
            auth_secret = 'xmlrpc:%s@' % auth_secret
        url = 'http://%s%s:%s' % (auth_secret, address[0], address[1])
        self._server = xmlrpclib.Server(url)


    def rpc(self, cmd, *args):
        """
        Call the remote command and return InProgress.
        """
        r = kaa.notifier.InProgress()
        t = kaa.notifier.Thread(getattr(self._server, cmd), *args)
        t.signals['completed'].connect(r.finished)
        t.signals['exception'].connect(r.exception)
        t.start()
        return r
