#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# nf_generic.py
#
# Author: Andreas Büsching <crunchy@tzi.de>
#
# generic notifier implementation
#
# $Id$
#
# Copyright (C) 2004, 2005 Andreas Büsching <crunchy@tzi.de>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.

"""Simple mainloop that watches sockets and timers."""

# python core packages
from copy import copy
from select import select
from select import error as select_error
import os, sys
import time
import logging
import socket

# get logging object
log = logging.getLogger('notifier')

IO_READ = 1
IO_WRITE = 2
IO_EXCEPT = 4

MIN_TIMER = 100

__sockets = {}
__sockets[ IO_READ ] = {}
__sockets[ IO_WRITE ] = {}
__sockets[ IO_EXCEPT ] = {}
__dispatchers = []
__timers = {}
__timer_id = 0
__min_timer = None

def millisecs():
    """returns the current time in milliseconds"""
    return int( time.time() * 1000 )

def addSocket( id, method, condition = IO_READ ):
    """The first argument specifies a socket, the second argument has to be a
    function that is called whenever there is data ready in the socket.
    The callback function gets the socket back as only argument."""
    global __sockets
    __sockets[ condition ][ id ] = method

def removeSocket( id, condition = IO_READ ):
    """Removes the given socket from scheduler. If no condition is specified the
    default is IO_READ."""
    global __sockets
    if __sockets[ condition ].has_key( id ):
        del __sockets[ condition ][ id ]

def addTimer( interval, method ):
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

    __timers[ __timer_id ] = ( interval, millisecs(), method )

    return __timer_id

def removeTimer( id ):
    """Removes the timer identifed by the unique ID from the main loop."""
    if __timers.has_key( id ):
        del __timers[ id ]

def addDispatcher( method ):
    """The notifier supports external dispatcher functions that will be called
    within each scheduler step. This functionality may be usful for
    applications having an own event mechanism that needs to be triggered as
    often as possible. This method registers a new dispatcher function. To
    ensure that the notifier loop does not suspend to long in the sleep state
    during the select a minimal timer MIN_TIMER is set to guarantee that the
    dispatcher functions are called at least every MIN_TIMER milliseconds."""
    global __dispatchers
    global __min_timer
    __dispatchers.append( method )
    __min_timer = MIN_TIMER

def removeDispatcher( method ):
    """Removes an external dispatcher function from the list"""
    global __dispatchers
    if method in __dispatchers:
        __dispatcher.remove( method )

def step( sleep = True, external = True ):
    # IDEA: Add parameter to specify max timeamount to spend in mainloop
    """Do one step forward in the main loop. First all timers are checked for
    expiration and if necessary the accociated callback function is called.
    After that the timer list is searched for the next timer that will expire.
    This will define the maximum timeout for the following select statement
    evaluating the registered sockets. Returning from the select statement the
    callback functions from the sockets reported by the select system call are
    invoked. As a final task in a notifier step all registered external
    dispatcher functions are invoked."""
    # handle timers
    trash_can = []
    _copy = __timers.copy()
    for i in _copy:
        interval, timestamp, callback = _copy[ i ]
        if interval + timestamp <= millisecs():
            retval = None
            try:
                if not callback():
                    trash_can.append( i )
                else:
                    __timers[ i ] = ( interval, millisecs(), callback )
            except ( KeyboardInterrupt, SystemExit ), e:
                raise e
            except:
                log.exception( 'removed timer %d' % i )
                trash_can.append( i )

    # remove functions that returned false from scheduler
    trash_can.reverse()
    for r in trash_can:
        if __timers.has_key( r ): del __timers[ r ]

    # get minInterval for max timeout
    timeout = None
    if not sleep:
        timeout = 0
    else:
        for t in __timers:
            interval, timestamp, callback = __timers[ t ]
            nextCall = interval + timestamp - millisecs()
            if timeout == None or nextCall < timeout:
                if nextCall > 0: timeout = nextCall
                else: timeout = 0
        if timeout == None: timeout = MIN_TIMER
        if __min_timer and __min_timer < timeout: timeout = __min_timer

    r = w = e = ()
    try:
        r, w, e = select( __sockets[ IO_READ ].keys(),
                          __sockets[ IO_WRITE ].keys(),
                          __sockets[ IO_EXCEPT ].keys(), timeout / 1000.0 )
    except ( ValueError, select_error ):
        log.exception( 'error in select' )
        sys.exit( 1 )

    for sl in ( ( r, IO_READ ), ( w, IO_WRITE ), ( e, IO_EXCEPT ) ):
        sockets, condition = sl
        for sock in sockets:
            if ( isinstance( sock, socket.socket ) and \
                 sock.fileno() != -1 ) or \
                   ( isinstance( sock, file ) and sock.fileno() != -1 ) or \
                   ( isinstance( sock, int ) and sock != -1 ):
                if __sockets[ condition ].has_key( sock ):
                    try:
                        if not __sockets[ condition ][ sock ]( sock ):
                            removeSocket( sock, condition )
                    except ( KeyboardInterrupt, SystemExit ), e:
                        raise e
                    except:
                        log.exception( 'error in socket callback' )
                        sys.exit( 1 )

    # handle external dispatchers
    if external:
        for disp in copy( __dispatchers ):
            try:
                disp()
            except ( KeyboardInterrupt, SystemExit ), e:
                raise e
            except:
                log.exception( 'error in dispatcher' )
                sys.exit( 1 )

def loop():
    """Executes the "main loop" forever by calling step in an endless loop"""
    while 1:
        step()
