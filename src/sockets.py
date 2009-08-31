# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# sockets.py - TCP/Unix Socket for the Kaa Framework
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# kaa.base - The Kaa Application Framework
# Copyright 2005-2009 Dirk Meyer, Jason Tackaberry, et al.
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

__all__ = [ 'Socket', 'SocketError' ]

import sys
import errno
import os
import re
import socket
import logging
import ctypes.util
import collections

from thread import threaded
from io import IO_READ, IO_WRITE, IOChannel
from utils import property, tempfile

# get logging object
log = logging.getLogger('base')



# Implement functions for converting between interface names and indexes.
# Unfortunately these functions are not provided by the standard Python
# socket library, so we must implement them ourselves with ctypes.

def _libc():
    """
    On-demand loading of libc.  Don't do this at initial import as the overhead
    is non-trivial.
    """
    try:
        return _libc._lib
    except AttributeError:
        pass

    _libc._lib = None
    if ctypes.util.find_library('c'):
        # ctypes in python >= 2.6 supports errno.
        kwargs = {'use_errno': True} if sys.hexversion >= 0x02060000 else {}
        _libc._lib = ctypes.CDLL(ctypes.util.find_library('c'), **kwargs)
    return _libc._lib


def if_nametoindex(name):
    """
    Returns the interface index number for the given interface name.

    :param name: name of the interface
    :type name: str
    :returns: integer of the interface id
    :raises: ValueError if the interface name cannot be found; 
             NotImplementedError on unsupported platforms.
    """
    try:
        idx = _libc().if_nametoindex(name)
    except AttributeError:
        raise NotImplementedError('Platform does not support if_nametoindex()')

    if idx <= 0:
        raise ValueError('Interface "%s" not found' % name)
    return idx


def if_indextoname(idx):
    """
    Returns the interface name for the given interface index number.

    :param idx: the index for the interface
    :type idx: int
    :returns: name of the index
    :raises: ValueError if the interface index is not found;
             NotImplementedError on unsupported platforms.
    """
    # Array must be at least IF_NAMESIZE, which is 16.  Double it for good measure.
    name = ctypes.create_string_buffer(32)
    try:
        ret = _libc().if_indextoname(idx, name)
    except AttributeError:
        raise NotImplementedError('Platform does not support if_indextoname()')

    if not ret:
        err = 'Failed to lookup interface index %d' % idx
        if hasattr(ctypes, 'get_errno'):
            err += ': ' + ctypes.c_char_p(_libc().strerror(ctypes.get_errno())).value
        raise ValueError(err)

    return name.value



class SocketError(Exception):
    pass

class Socket(IOChannel):
    """
    Communicate over TCP or Unix sockets, implementing fully asynchronous reads
    and writes.

    kaa.Socket requires an IPv6-capable stack, and favors IPv6 connectivity
    when available.  This should generally be completely transparent on
    IPv4-only networks.  See :meth:`~kaa.Socket.connect` for more information.
    """
    __kaasignals__ = {
        'new-client':
            '''
            Emitted when a new client connects to a listening socket.

            ``def callback(client, ...)``

            :param client: the new client that just connected.
            :type client: :class:`~kaa.Socket` object
            '''
    }

    def __init__(self, buffer_size=None, chunk_size=1024*1024):
        self._connecting = False
        self._listening = False
        self._buffer_size = buffer_size
        # Requested hostname passed to connect()
        self._reqhost = None

        super(Socket, self).__init__(chunk_size=chunk_size)


    @IOChannel.fileno.getter
    def fileno(self):
        # If fileno() is accessed on a closed socket, socket.error is
        # railsed.  So we override our superclass's implementation to
        # handle this case.
        try:
            return self._channel.fileno()
        except (AttributeError, socket.error):
            return None


    @property
    def address(self):
        """
        This property is deprecated; use *peer* instead.
        """
        log.warning('Socket.address is deprecated; use Socket.peer instead')
        return self.local[:2]


    @property
    def local(self):
        """
        Returns either the tuple ``(host, port, flowinfo, scopeid, scope)``
        representing the local end of a TCP socket, or the string containing
        the name of a Unix socket.
        
        *scope* is the interface name represented by *scopeid*, and is None if
        *scopeid* is 0.

        On Python 2.6 and later, the returned value is a namedtuple.
        """
        return self._make_address_tuple(self._channel.getsockname())


    @property
    def peer(self):
        """
        Returns the tuple ``(host, port, flowinfo, scopeid, scope, reqhost)``
        representing the remote end of the socket.
        
        *scope* is the interface name represented by *scopeid*, and is None if
        *scopeid* is 0.  *reqhost* is the requested hostname if
        :meth:`~kaa.Socket.connect` was called, or None if this is a listening
        socket.

        On Python 2.6 and later, the returned value is a namedtuple.
        """
        return self._make_address_tuple(self._channel.getpeername(), self._reqhost)


    @property
    def listening(self):
        """
        True if this is a listening socket, and False otherwise.
        """
        return self._listening


    @property
    def connecting(self):
        """
        True if the socket is in the process of establishing a connection
        but is not yet connected.
        
        Once the socket is connected, the connecting property will be False,
        but the connected property will be True.
        """
        return self._connecting


    @property
    def connected(self):
        """
        Boolean representing the connected state of the socket.
        """
        try:
            # Will raise exception if socket is not connected.
            self._channel.getpeername()
            return True
        except (AttributeError, socket.error):
            # AttributeError is raised if _channel is None, socket.error is
            # raised if the socket is disconnected
            return False


    @property
    def alive(self):
        """
        True if the socket is alive, and False otherwise.

        A socket is considered alive when it is connected or in the process of
        connecting.
        """
        return self.connected or self.connecting


    @IOChannel.readable.getter
    def readable(self):
        """
        True if the socket is readable, and False otherwise.
        
        A socket is considered readable when it is listening or alive.
        """
        # Note: this property is used in superclass's _update_read_monitor()
        return self._listening or self.alive


    @property
    def buffer_size(self):
        """
        Size of the send and receive socket buffers (SO_SNDBUF and SO_RCVBUF)
        in bytes.
        
        Setting this to higher values (say 1M) improves performance when
        sending large amounts of data across the socket.  Note that the upper
        bound may be restricted by the kernel.  (Under Linux, this can be tuned
        by adjusting /proc/sys/net/core/[rw]mem_max)
        """
        return self._buffer_size


    @buffer_size.setter
    def buffer_size(self, size):
        self._buffer_size = size
        if self._channel and size:
            self._set_buffer_size(self._channel, size)


    def _set_buffer_size(self, s, size):
        """
        Sets the send and receive buffers of the given socket s to size.
        """
        s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, size)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, size)


    def _make_address_tuple(self, addr, *args):
        """
        Converts an AF_INET6 socket address to a 5- or 6-tuple for use with the
        *local* and *peer* properties.  IPv4-mapped IPv6 addresses are
        converted to standard IPv4 dotted quads.

        On Python 2.6 and later, this returns a namedtuple.
        """
        if isinstance(addr, basestring):
            # Unix socket
            return addr

        try:
            scope = if_indextoname(addr[3])
        except (ValueError, NotImplementedError):
            scope = None

        reqhost = args[0] if args else None
        ip = addr[0][7:] if addr[0].lower().startswith('::ffff:') else addr[0]
        addr = (ip,) + addr[1:] + (scope,) + ((reqhost,) if args else ())
        if sys.hexversion < 0x02060000:
            return addr

        fields = 'host port flowinfo scopeid scope' + (' reqhost' if args else '')
        return collections.namedtuple('address', fields)(*addr)


    def _normalize_address(self, addr):
        """
        Converts supported address formats into a normalized 4-tuple (hostname,
        port, flowinfo, scope).  See connect() and listen() for supported
        formats.

        Service names are resolved to port numbers, and interface names are
        resolved to scope ids.  However, hostnames are not resolved to IPs
        since that can block.  Unspecified port or interface name will produced
        0 values for those fields.

        A non-absolute unix socket name will converted to a full path using
        kaa.tempfile().

        If we can't make sense of the given address, a ValueError exception will
        be raised.
        """
        if isinstance(addr, basestring):
            if ':' not in addr:
                # Treat as unix socket.
                return tempfile(addr) if not addr.startswith('/') else addr

            m = re.match(r'^ (\[(?:[\da-fA-F:]+)\] | (?:[^:]+) )? (?::(\w+))? (?:%(\w+))? ', addr, re.X)
            if not m:
                raise ValueError('Invalid format for address')
            addr = m.group(1) or '', m.group(2) or 0, 0, m.group(3) or 0
            if addr[0].isdigit():
                # Sanity check: happens when given ipv6 address without []
                raise ValueError('Invalid hostname: perhaps ipv6 address is not wrapped in []?')

        elif not isinstance(addr, (tuple, list)) or len(addr) != 4:
            raise ValueError('Invalid address specification (must be str, or 4-tuple)')

        host, service, flowinfo, scopeid = addr
        # Strip [] from ipv6 addr
        if host.startswith('[') and host.endswith(']'):
            host = host[1:-1]
        # Resolve service name to port number
        if isinstance(service, basestring):
            service = int(service) if service.isdigit() else socket.getservbyname(service)
        # Resolve interface names to index values
        if isinstance(scopeid, basestring):
            scopeid = int(scopeid) if scopeid.isdigit() else if_nametoindex(scopeid) 

        return host, service, flowinfo, scopeid


    def _make_socket(self, addr=None, overwrite=False):
        """
        Constructs a socket based on the given addr.  Returns the socket and
        the normalized address as a 2-tuple.

        If overwrite is True, if addr specifies a path to a unix socket and
        that unix socket already exists, it will be removed if the socket is
        not actually in use.  If it is in use, an IOError will be raised.
        """
        addr = self._normalize_address(addr)
        assert(type(addr) in (str, tuple, None))

        if isinstance(addr, str):
            if overwrite and os.path.exists(addr):
                # Unix socket exists; test to see if it's active.
                try:
                    dummy = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    dummy.connect(addr)
                except socket.error, (err, msg):
                    if err == errno.ECONNREFUSED:
                        # Socket is not active, so we can remove it.
                        log.debug('Replacing dead unix socket at %s' % addr)
                    else:
                        # Reraise unexpected exception
                        tp, exc, tb = sys.exc_info()
                        raise tp, exc, tb
                else:
                    # We were able to connect to the existing socket, so it's
                    # in use.  We won't overwrite it.
                    raise IOError('Address already in use')
                os.unlink(addr)

            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        else:
            sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        return sock, addr


    def listen(self, bind_info, qlen=5):
        """
        Sets the socket to listen.

        :param bind_info: Binds the socket using this value.  If an int, this
                          specifies a TCP port that is bound on all interfaces; if a
                          str, it is either a Unix socket path or represents a TCP
                          socket when in the form ``[host]:[service][%scope]``.  
                          See below for further details.
        :type bind_info: int, str, or 4-tuple
        :raises: ValueError if *bind_info* is invalid, or socket.error if the bind fails.

        If *addr* is given as a tuple, it is in the form ``(host, service,
        flowinfo, scope)``.  See :meth:`~kaa.Socket.connect` for more
        information.

        If *addr* is given as a string, it is treated as a Unix socket path if it
        does not contain ``:``, otherwise it is specified as ``[host]:[service][%scope]``,
        where ``[x]`` indicates that ``x`` is optional, and where:

            * *host* is a hostname, an IPv4 dotted quad, or an IPv6 address
              wrapped in square brackets.  e.g. freevo.org, 192.168.0.1,
              [3000::1]
            * *service* is a service name or port number.  e.g. http, 80
            * *scope* is an interface name or number.  e.g. eth0, 2

        When binding to a link-local address (``fe80::/16``), *scope* must be
        specified.  Relative Unix socket names (those not prefixed with
        ``/``) are created via kaa.tempfile.

        Once listening, new connections are automatically accepted, and the
        :attr:`~kaa.Socket.signals.new-client` signal is emitted for each new
        connection.  Callbacks connecting to the signal will receive a new
        Socket object representing the client connection.
        """
        if isinstance(bind_info, int):
            # Only port number specified; translate to tuple that can be
            # used with socket.bind()
            bind_info = ('', bind_info, 0, 0)

        sock, addr = self._make_socket(bind_info, overwrite=True)

        # If link-local address is specified, make sure the scopeid is given.
        if addr[0].lower().startswith('fe80::'):
            if not addr[3]:
                raise ValueError('Binding to a link-local address requires scopeid')

        sock.bind(addr)
        sock.listen(qlen)
        self._listening = True
        self.wrap(sock, IO_READ | IO_WRITE)


    @threaded()
    def _connect(self, addr, ipv6=True):
        sock, addr = self._make_socket(addr)
        try:
            if type(addr) == str:
                # Unix socket, just connect.
                sock.connect(addr)
                self._reqhost = addr
            else:
                self._reqhost = addr[0]
                # Resolve host (or ip) into IPs.  At least on Linux, returned
                # list is ordered to prefer IPv6 addresses provided that a
                # route is available to them.  We try all addresses until we
                # get a connection, and if all addresses fail, then we raise
                # the _first_ exception.
                err = None
                addrs = socket.getaddrinfo(addr[0], addr[1], socket.AF_INET6 if ipv6 else socket.AF_INET,
                                           socket.SOCK_STREAM, 0, socket.AI_V4MAPPED | socket.AI_ALL)
                for addrinfo in (a[4] for a in addrs):
                    try:
                        if not ipv6:
                            # Only IPv4 addresses requested, so getaddrinfo will not return
                            # IPv4-mapped IPv6 addresses, but because our socket is AF_INET6
                            # we still must map them.
                            addrinfo = ('::ffff:' + addrinfo[0],) + addrinfo[1:]
                        sock.connect(addrinfo)
                        break
                    except socket.error, e:
                        err = sys.exc_info() if not err else err
                else:
                    raise err[0], err[1], err[2]
        finally:
            self._connecting = False

        self.wrap(sock, IO_READ | IO_WRITE)


    def connect(self, addr, ipv6=True):
        """
        Connects to the host specified in address.

        :param addr: Address for a remote host, or a Unix socket.  If a str,
                     it is either a Unix socket path or represents a TCP
                     socket when in the form ``host:service[%scope]``.  See
                     below for further details.
        :type addr: str or 4-tuple
        :param ipv6: if True, will connect to the remote host using IPv6 if
                     it is reachable via IPv6.  This is perfectly safe for IPv4
                     only hosts too.  Set this to False if the remote host
                     has a AAAA record and the local host has an IPv6 route to
                     it, but you want to force IPv4 anyway.
        :returns: An :class:`~kaa.InProgress` object.

        If *addr* is given as a tuple, it is in the form ``(host, service,
        flowinfo, scope)``.  The *flowinfo* and *scope* fields are only
        relevant for IPv6 hosts, where they represent the ``sin6_flowinfo`` and
        ``sin6_scope_id`` members in :const:`struct sockaddr_in6` in C.
        *scope* may be the name of an interface (e.g. ``eth0``) or an interface
        id, and is needed when connecting to link-local addresses
        (``fe80::/16``).

        If *addr* is given as a string, it is treated as a Unix socket path if it
        does not contain ``:``, otherwise it is specified as ``host:service[%scope]``,
        where ``[x]`` indicates that ``x`` is optional, and where:

            * *host* is a hostname, an IPv4 dotted quad, or an IPv6 address
              wrapped in square brackets.  e.g. freevo.org, 192.168.0.1,
              [3000::1]
            * *service* is a service name or port number.  e.g. http, 80
            * *scope* is an interface name or number.  e.g. eth0, 2

        When connecting to a link-local address (fe80::/16), *scope* must be
        specified.  Relative Unix socket names (those not prefixed with ``/``)
        are created via kaa.tempfile.

        This function is executed in a thread to avoid blocking.  It therefore
        returns an InProgress object.  If the socket is connected, the InProgress
        is finished with no arguments.  If the connection cannot be established,
        an exception is thrown to the InProgress.
        """
        self._connecting = True
        return self._connect(addr, ipv6)


    def wrap(self, sock, mode=IO_READ|IO_WRITE):
        """
        Wraps an existing low-level socket object.
        
        addr specifies the 4-tuple address corresponding to the socket.
        """
        super(Socket, self).wrap(sock, mode)
        if self._buffer_size:
            self._set_buffer_size(sock, self._buffer_size)


    def _is_read_connected(self):
        return self._listening or super(Socket, self)._is_read_connected()


    def _set_non_blocking(self):
        self._channel.setblocking(False)


    def _read(self, size):
        return self._channel.recv(size)


    def _write(self, data):
        return self._channel.send(data)


    def _accept(self):
        """
        Accept a new connection and return a new Socket object.
        """
        sock, addr = self._channel.accept()
        # create new Socket from the same class this object is
        client_socket = self.__class__()
        client_socket.wrap(sock, IO_READ | IO_WRITE)
        self.signals['new-client'].emit(client_socket)


    def _handle_read(self):
        if self._listening:
            return self._accept()

        return super(Socket, self)._handle_read()


    def _close(self):
        super(Socket, self)._close()
        self._reqhost = None
        if self._listening and isinstance(self.local, basestring) and self.local.startswith('/'):
            # Remove unix socket if it exists.
            try:
                os.unlink(self.local)
            except OSError:
                pass


    def steal(self, socket):
        if not isinstance(socket, Socket):
            raise TypeError('Can only steal from other sockets')

        self._buffer_size = socket._buffer_size
        return super(Socket, self).steal(socket)
