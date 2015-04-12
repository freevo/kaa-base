# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# nf_wrapper.py - wrap pynotifier in kaa-aware objects
# -----------------------------------------------------------------------------
# kaa.base - The Kaa Application Framework
# Copyright 2006-2012 Dirk Meyer, Jason Tackaberry, et al.
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
from __future__ import absolute_import

# Python imports
import logging
import sys
import atexit

# notifier import
from .callable import Callable, WeakCallable, CallableError
from .utils import property
# use our own copy of pynotifier
from . import nf_generic

# get logging object
log = logging.getLogger('kaa.base.core.main')

# Variable that is set to True (via atexit callback) when python interpreter
# is in the process of shutting down.  If we're interested if the interpreter
# is shutting down, we don't want to test that this variable is True, but
# rather that it is not False, because as it is prefixed with an underscore,
# the interpreter might already have deleted this variable in which case it
# is None.
_python_shutting_down = False

loaded = False

class NotifierCallback(Callable):
    """
    Callback class for the generic notifier
    """
    def __init__(self, callback, *args, **kwargs):
        super(NotifierCallback, self).__init__(callback, *args, **kwargs)
        self._id = None

    @property
    def active(self):
        """
        True if the callback is registered with the notifier.
        """
        # callback is active if id is not None and python is not shutting down
        # if python is in shutdown, notifier unregister could crash
        return self._id != None and _python_shutting_down == False

    def unregister(self):
        # Unregister callback with notifier.  Must be implemented by subclasses.
        self._id = None

    def __call__(self, *args, **kwargs):
        if not self._get_func():
            if self.active:
                self.unregister()
            return False
        try:
            ret = super(NotifierCallback, self).__call__(*args, **kwargs)
        except CallableError:
            # A WeakCallable that's no longer valid.  Unregister.
            ret = False

        # If Notifier callbacks return False, they get unregistered.
        if ret == False:
            self.unregister()
            return False
        return True


class WeakNotifierCallback(WeakCallable, NotifierCallback):
    """
    Weak Callback class for the generic notifier
    """
    def _weakref_destroyed(self, object):
        if _python_shutting_down == False:
            super(WeakNotifierCallback, self)._weakref_destroyed(object)
            self.unregister()


timer_remove = nf_generic.timer_remove
timer_add = nf_generic.timer_add

step = nf_generic.step

def shutdown():
    # prefered way to shut down the system
    sys.exit(0)

# socket wrapper

nf_conditions = []
def _socket_add(id, method, condition = 0):
    return nf_socket_add(id, method, nf_conditions[condition])


def _socket_remove(id, condition = 0):
    return nf_socket_remove(id, nf_conditions[condition])

nf_socket_remove = nf_generic.socket_remove
nf_socket_add = nf_generic.socket_add
nf_conditions = [ nf_generic.IO_READ, nf_generic.IO_WRITE, nf_generic.IO_EXCEPT ]
socket_remove = _socket_remove
socket_add = _socket_add


def init( module = None, force_internal=False, **options ):
    loaded = True


def _shutdown_weakref_destroyed():
    global _python_shutting_down
    _python_shutting_down = True

atexit.register(_shutdown_weakref_destroyed)
