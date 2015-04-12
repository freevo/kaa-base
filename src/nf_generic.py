#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Author: Andreas Büsching <crunchy@bitkipper.net>
# Modified for kaa.base by Dirk Meyer and Jason Tackaberry
#
# generic notifier implementation
#
# Copyright 2004, 2005, 2006, 2007
#    Andreas Büsching <crunchy@bitkipper.net>
#
# This library is free software; you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License version
# 2.1 as published by the Free Software Foundation.
#
# This library is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.    See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301 USA


# python core packages
import logging
from select import select
from select import error as select_error
from time import time, sleep as time_sleep
import errno, os, sys
import socket

# get logging object
log = logging.getLogger('kaa.base.core.main')

IO_READ = 1
IO_WRITE = 2
IO_EXCEPT = 4
( INTERVAL, TIMESTAMP, CALLBACK ) = range( 3 )

__sockets = {}
__sockets[ IO_READ ] = {}
__sockets[ IO_WRITE ] = {}
__sockets[ IO_EXCEPT ] = {}
__timers = {}
__timer_id = 0
__min_timer = None
__step_depth = 0
__step_depth_max = 5

def socket_add( id, method, condition = IO_READ ):
    """The first argument specifies a socket, the second argument has to be a
    function that is called whenever there is data ready in the socket.
    The callback function gets the socket back as only argument."""
    global __sockets
    __sockets[ condition ][ id ] = method

def socket_remove( id, condition = IO_READ ):
    """Removes the given socket from scheduler. If no condition is specified the
    default is IO_READ."""
    global __sockets
    if id in __sockets[ condition ]:
        del __sockets[ condition ][ id ]

def timer_add( interval, method ):
    """The first argument specifies an interval in milliseconds, the second
    argument a function. This is function is called after interval
    seconds. If it returns true it's called again after interval
    seconds, otherwise it is removed from the scheduler. The third
    (optional) argument is a parameter given to the called
    function. This function returns an unique identifer which can be
    used to remove this timer"""
    global __timer_id
    try:
        __timer_id += 1
    except OverflowError:
        __timer_id = 0
    __timers[ __timer_id ] = \
    [ interval, int( time() * 1000 ) + interval, method ]
    return __timer_id

def timer_remove( id ):
    """Removes the timer identifed by the unique ID from the main loop."""
    if id in __timers:
        del __timers[ id ]

def step( sleep = True, external = True, simulate = False ):
    """Do one step forward in the main loop. First all timers are checked for
    expiration and if necessary the accociated callback function is called.
    After that the timer list is searched for the next timer that will expire.
    This will define the maximum timeout for the following select statement
    evaluating the registered sockets. Returning from the select statement the
    callback functions from the sockets reported by the select system call are
    invoked. As a final task in a notifier step all registered external
    dispatcher functions are invoked."""
    global __step_depth
    __step_depth += 1
    try:
        if __step_depth > __step_depth_max:
            log.exception( 'maximum recursion depth reached' )
            return
        # get minInterval for max timeout
        timeout = None
        if not sleep:
            timeout = 0
        else:
            now = int( time() * 1000 )
            for interval, timestamp, callback in __timers.values():
                if not timestamp:
                    # timer is blocked (recursion), ignore it
                    continue
                nextCall = timestamp - now
                if timeout == None or nextCall < timeout:
                    if nextCall > 0:
                        timeout = nextCall
                    else:
                        timeout = 0
                        break
            if timeout == None:
                # No timers, timeout could be infinity.
                timeout = 30000
            if __min_timer and __min_timer < timeout: timeout = __min_timer
        # wait for event
        sockets_ready = None
        if __sockets[ IO_READ ] or __sockets[ IO_WRITE ] or __sockets[ IO_EXCEPT ]:
            try:
                sockets_ready = select( __sockets[ IO_READ ].keys(), __sockets[ IO_WRITE ].keys(),
                                        __sockets[ IO_EXCEPT ].keys(), timeout / 1000.0 )
            except select_error, e:
                if e.args[ 0 ] != errno.EINTR:
                    raise e
        elif timeout:
            time_sleep(timeout / 1000.0)
        if simulate:
            # we only simulate
            return
        # handle timers
        for i, timer in __timers.items():
            timestamp = timer[ TIMESTAMP ]
            if not timestamp or i not in __timers:
                # timer was unregistered by previous timer, or would
                # recurse, ignore this timer
                continue
            now = int( time() * 1000 )
            if timestamp <= now:
                # Update timestamp on timer before calling the callback to
                # prevent infinite recursion in case the callback calls
                # step().
                timer[ TIMESTAMP ] = 0
                if not timer[ CALLBACK ]():
                    if i in __timers:
                        del __timers[ i ]
                else:
                    # Find a moment in the future. If interval is 0, we
                    # just reuse the old timestamp, doesn't matter.
                    if timer[ INTERVAL ]:
                        now = int( time() * 1000 )
                        timestamp += timer[ INTERVAL ]
                        while timestamp <= now:
                            timestamp += timer[ INTERVAL ]
                    timer[ TIMESTAMP ] = timestamp
        # handle sockets
        if sockets_ready:
            for condition, sockets in zip((IO_READ, IO_WRITE, IO_EXCEPT), sockets_ready):
                for sock in sockets:
                    # XXX: Not quite sure why these checks are done, since select()
                    # would have raised on these first.
                    try:
                        if isinstance(sock, int):
                            assert(sock != -1)
                        else:
                            assert(getattr(sock, 'closed', False) == False)
                            assert(sock.fileno() != -1)
                    except (AssertionError, socket.error, ValueError):
                        # socket is either closed or not supported.
                        socket_remove( sock, condition )
                        continue
                    # the timer handling might have removed a socket from the
                    # list and therefore sock is not in __sockets[ condition ]
                    # anymore.
                    callback = __sockets[ condition ].get(sock)
                    if callback is not None and not callback( sock ):
                        socket_remove( sock, condition )
    finally:
        __step_depth -= 1
