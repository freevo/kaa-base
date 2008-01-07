#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Author: Rob Shortt <rob@tvcentric.com>
#
# A notifier implementation using Twisted.
#
# Copyright (C) 2008
# Rob Shortt <rob@tvcentric.com>
#
# This library is free software; you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License version
# 2.1 as published by the Free Software Foundation.
#
# This library is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.	See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301 USA

"""
This is a notifier implementation using Twisted - http://www.twistedmatrix.com/
Twisted is an async framework that has much in common with pynotifier and kaa.

Here are some links of interest to aid development and debuging:

The reactor base class, posixbase, and selectreactor:
http://twistedmatrix.com/trac/browser/trunk/twisted/internet/base.py
http://twistedmatrix.com/trac/browser/trunk/twisted/internet/posixbase.py
http://twistedmatrix.com/trac/browser/trunk/twisted/internet/selectreactor.py

Timers and scheduling:
http://twistedmatrix.com/projects/core/documentation/howto/time.html

Twisted doc index:
http://twistedmatrix.com/projects/core/documentation/howto/index.html
"""

# Twisted uses zope.interface
from zope.interface import implements

# Twisted imports
from twisted.internet.interfaces import IReadDescriptor, IWriteDescriptor
from twisted.internet import reactor
from twisted.internet import task

# internal packages
import dispatch

IO_READ = 1
IO_WRITE = 2
IO_EXCEPT = 4

__sockobjs = {}
__sockobjs[IO_READ] = {}
__sockobjs[IO_WRITE] = {}
__timers = {}
__timer_id = 0
__dispatch_timer = None


class SocketReadCB:
    """
    An object to implement Twisted's IReadDescriptor.  When there is data 
    available on the socket doRead() will get called.
    """
    implements(IReadDescriptor)

    def __init__(self, socket, method):
        self.socket = socket
        self.method = method

    def doRead(self):
        """
        Call the callback method with the socket as the only argument.  If it
        returns False remove this socket from our notifier.
        """
        if self.method(self.socket) == False:
            socket_remove(self.socket, IO_READ)

    def fileno(self):
        # FIXME: check is socket is a socket or int
        return self.socket

    def logPrefix(self):
        # FIXME: debug and improve if needed
        return "doRead: "

    def connectionLost(self, reason): 
        # FIXME: debug and improve if needed
        print "connectionLost"


class SocketWriteCB:
    """
    An object to implement Twisted's IWriteDescriptor.  When there is data 
    available on the socket doWrite() will get called.
    """
    implements(IWriteDescriptor)

    def __init__(self, socket, method):
        self.socket = socket
        self.method = method

    def doWrite(self):
        """
        Call the callback method with the socket as the only argument.  If it
        returns False remove this socket from our notifier.
        """
        if self.method(self.socket) == False:
            socket_remove(self.socket, IO_WRITE)

    def fileno(self):
        # FIXME: check is socket is a socket or int
        return self.socket

    def logPrefix(self):
        # FIXME: debug and improve if needed
        return "doWrite: "

    def connectionLost(self, reason): 
        # FIXME: debug and improve if needed
        print "connectionLost"


def socket_add(id, method, condition = IO_READ):
    """
    The first argument specifies a socket, the second argument has to be a
    function that is called whenever there is data ready in the socket.

    Objects that implement Twisted's IRead/WriteDescriptor interfaces get
    passed to the reactor to monitor.
    """
    global __sockobjs

    if condition == IO_READ:
        s = SocketReadCB(id, method)
        reactor.addReader(s)

    elif condition == IO_WRITE:
        s = SocketWriteCB(id, method)
        reactor.addWriter(s)

    else:
        return

    __sockobjs[condition][id] = s


def socket_remove(id, condition=IO_READ):
    """
    Removes the IRead/WriteDescriptor object with this socket from
    the Twisted reactor.
    """
    global __sockobjs
    sockobj = __sockobjs[condition].get(id)

    if sockobj:
        if condition == IO_READ:
            reactor.removeReader(sockobj)
        elif condition == IO_WRITE:
            reactor.removeWriter(sockobj)
        del __sockobjs[condition][id]


def timer_add(interval, method):
    """
    The first argument specifies an interval in milliseconds, the second
    argument a function. This is function is called after interval
    seconds. If it returns true it's called again after interval
    seconds, otherwise it is removed from the scheduler. The third
    (optional) argument is a parameter given to the called
    function. This function returns an unique identifer which can be
    used to remove this timer
    """
    global __timer_id

    try:
        __timer_id += 1
    except OverflowError:
        __timer_id = 0

    t = task.LoopingCall(method)
    t.start(interval/1000.0, now=False)
    __timers[__timer_id] = t 

    return __timer_id


def timer_remove(id):
    """
    Removes the timer identifed by the unique ID from the main loop.
    """
    t = __timers.get(id)
    if t != None:
        t.stop()
        del __timers[id]


def dispatcher_add(method):
    dispatch.dispatcher_add(method)

dispatcher_remove = dispatch.dispatcher_remove


def step(sleep = True, external = True, simulate = False):
    global __timers

    reactor.runUntilCurrent()
    t2 = reactor.timeout()
    t = reactor.running and t2
    reactor.doIteration(t)


def loop():
    reactor.run()


def _init():
    global __dispatch_timer
    __dispatch_timer = task.LoopingCall(dispatch.dispatcher_run)
    __dispatch_timer.start(dispatch.MIN_TIMER/1000.0)

    reactor.startRunning(installSignalHandlers=True)

