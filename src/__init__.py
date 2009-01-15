# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# __init__.py - main kaa init module
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# Copyright (C) 2005-2008 Dirk Meyer, Jason Tackaberry
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

# import logger to update the Python logging module
import logger

# We have some problems with recursive imports. One is InProgress from
# async. It is a Signal, but Signal itself has an __inprogress__
# function. To avoid any complications, we import async first. This
# will import other file that require InProgress. To avoid problems,
# these modules only import async as complete module, not InProgress
# inside async because it does not exist yet.

# InProgress class
from async import TimeoutException, InProgress, InProgressCallback, \
     InProgressAny, InProgressAll, inprogress, delay

# Import all classes, functions and decorators that are part of the API
from object import Object

# Callback classes
from callback import Callback, WeakCallback

# Signal and dict of Signals
from signals import Signal, Signals

# Thread callbacks, helper functions and decorators
from thread import MainThreadCallback, NamedThreadCallback, ThreadCallback, \
     is_mainthread, threaded, synchronized, MAINTHREAD

# Timer classes and decorators
from timer import Timer, WeakTimer, OneShotTimer, WeakOneShotTimer, AtTimer, \
     OneShotAtTimer, timed, POLICY_ONCE, POLICY_MANY, POLICY_RESTART

# IO/Socket handling
from io import IOMonitor, WeakIOMonitor, IO_READ, IO_WRITE, IOChannel
from sockets import Socket, SocketError

# Event and event handler classes
from event import Event, EventHandler, WeakEventHandler

# coroutine decorator and helper classes
from coroutine import NotFinished, coroutine, \
     POLICY_SYNCHRONIZED, POLICY_SINGLETON, POLICY_PASS_LAST

# process management
from popen import Process
from process import Process2

# special gobject thread support
from gobject import GOBJECT, gobject_set_threaded

# Import the two important strutils functions
from strutils import str_to_unicode, unicode_to_str

# Add tempfile support.
from utils import tempfile

# Expose main loop functions under kaa.main
import main
from main import signals
