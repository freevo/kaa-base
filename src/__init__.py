# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# __init__.py - main kaa init module
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# Copyright 2005-2009 Dirk Meyer, Jason Tackaberry
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

# Declare 'kaa' namespace for setuptools.
try:
    # http://peak.telecommunity.com/DevCenter/setuptools#namespace-packages
    # offers a stern admonition that after declaring a namespace, we must not
    # add any other code to __init__.py.  However, this isn't possible for us,
    # and, near as I can tell, our approach is safe because kaa sub-modules
    # don't include kaa/__init__.py.  The only module that does is kaa.base.
    # So there's no risk of some other egg getting loaded when we do 'import
    # kaa'.
    #
    # See below for more discussion.
    __import__('pkg_resources').declare_namespace('kaa')
except ImportError:
    # No setuptools installed, no egg support.
    pass

# import logger to update the Python logging module
import logger

# TODO: importing kaa is a bit expensive, and this is especially relevant when
# some submodule kaa.foo is imported which doesn't end up using much of kaa.base.
# We would benefit from lazy imports on everything below.

# We have some problems with recursive imports. One is InProgress from
# async. It is a Signal, but Signal itself has an __inprogress__
# function. To avoid any complications, we import async first. This
# will import other file that require InProgress. To avoid problems,
# these modules only import async as complete module, not InProgress
# inside async because it does not exist yet.

# InProgress class
from async import TimeoutException, InProgress, InProgressCallable, \
     InProgressAny, InProgressAll, InProgressAborted, InProgressStatus, \
     inprogress, delay

# Import all classes, functions and decorators that are part of the API
from object import Object

# Callable classes
from callable import Callable, WeakCallable, CallableError

# Notifier-aware callbacks
from nf_wrapper import NotifierCallback, WeakNotifierCallback

# Signal and dict of Signals
from signals import Signal, Signals

# Thread callables, helper functions and decorators
from thread import MainThreadCallable, ThreadPoolCallable, ThreadCallable, \
     is_mainthread, threaded, synchronized, MAINTHREAD, ThreadInProgress, \
     ThreadPool, register_thread_pool, get_thread_pool

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

# generator support
from generator import Generator, generator

# process management
from process import Process

# special gobject thread support
from gobject import GOBJECT, gobject_set_threaded

# Import the two important strutils functions
from strutils import str_to_unicode, unicode_to_str

# Add tempfile support.
from utils import tempfile

# Expose main loop functions under kaa.main
import main
from main import signals

import sys, os
if sys.hexversion < 0x02060000 and os.name == 'posix':
    # Python 2.5 (all point releases) have a bug with listdir on POSIX systems
    # causing improper out of memory exceptions.  We replace the standard
    # os.listdir with a version from kaa._utils that doesn't have this bug.
    # Some distros will have patched their 2.5 packages, but since we can't
    # discriminate those, we replace os.listdir regardless.
    #
    # See http://bugs.python.org/issue1608818
    import kaa._utils
    os.listdir = kaa._utils.listdir



# So, we have a little bit of a problem if we use eggs.  Because 'kaa' is
# rather non-standardly _both_ a namespace (holding other modules like beacon,
# imlib2, etc.) _and_ a module (kaa.base), any kaa module not installed the
# same way as kaa.base (on-disk tree or egg) would not be found during import.
# 
# kaa.base (egg or tree) seems to be reliably imported when 'kaa' is imported,
# as opposed to some other module (egg or tree), presumably because kaa.base is
# the only module that defines kaa/__init__.py.  However, if kaa.base is an egg
# and some module kaa.foo is not, or vice versa, subsequent 'import kaa.foo'
# will fail because foo/ does not exist inside kaa.base.  This is not a problem
# when all modules are installed as on-disk trees, but it does become a problem
# when eggs are used.
#
# Another ugly but possible scenario is if we have a mix of eggs and non-eggs,
# e.g. kaa.base is an egg and kaa.foo is an on-disk source tree, or vice versa.
# This means, given kaa.base and module kaa.foo, we have 4 possibilities:
#
#   1. kaa.base as egg, kaa.foo as egg
#   2. kaa.base as egg, kaa.foo as source tree
#   3. kaa.base as source tree, kaa.foo as egg
#   4. kaa.base as source tree, kaa.foo as source tree
#
# The import trickery (which is always scary) below deals with these 
# scenarios.
#
# We add a custom finder to sys.meta_path so that when the user later does
# 'import kaa.foo' we'll zipimport a kaa_foo egg if it existed at start time,
# or properly load kaa/foo/__init__.py if kaa.foo is installed as an on-disk
# tree while kaa.base is an egg.

class KaaLoader:
    """
    Custom import hook loader module loader, used when importing non-egg
    kaa modules if other kaa modules are installed as eggs.  In other
    words, this class is unused when everything is installed as eggs,
    or when everything is installed as on-disk source trees.
    """
    def __init__(self, info):
        self._info = info

    def load_module(self, name):
        if name in sys.modules:
            return sys.modules[name]

        # Import imp in here so as not to pollute kaa namespace.
        import imp
        try:
            # Try form kaa/foo/__init__.py
            mod = imp.load_module(name[4:], *self._info)
            mod.__name__ = name
        except ImportError:
            # Try form kaa/foo.py
            mod = imp.load_module(name, *self._info)

        sys.modules[name] = mod
        return mod
        

class KaaFinder:
    def __init__(self):
        self.kaa_eggs = {}
        for mod in sys.path:
            name = os.path.basename(mod)
            if name.startswith('kaa_') and mod.endswith('.egg'):
                # This is a kaa egg.  Convert kaa_foo-0.1.2.egg filename to
                # kaa.foo module name
                submod_name = 'kaa.' + name[4:].split('-')[0]
                self.kaa_eggs[submod_name] = mod

    def find_module(self, name, path):
        # Bypass import hooks if module isn't in the form kaa.foo.  We also
        # don't need any custom import hooks if there are no kaa eggs.  If
        # everything kaa is installed as an on-disk source tree, there is
        # no problem that needs solving.
        if not name.startswith('kaa.') or name.count('.') > 1 or not self.kaa_eggs:
            return

        if name not in self.kaa_eggs or os.path.isdir(self.kaa_eggs[name]):
            # There's no egg, or the egg is actually uncompressed as an
            # on-disk tree (i.e. kaa_foo.egg is actually a directory).
            try:
                import imp
                info = imp.find_module(name.replace('.', '/'), sys.path)
            except ImportError:
                return
            return KaaLoader(info)

        # Egg is available for requested module, so attempt to import it.
        import zipimport
        o = zipimport.zipimporter(self.kaa_eggs[name] + '/kaa')
        return o

# Now install our custom hooks.
sys.meta_path.append(KaaFinder())



# Allow access to old Callback names, but warn.  This will go away the release
# after next (probably 0.99.1).
def rename(oldcls, newcls):
    class Wrapper(__builtins__['object']):
        def __new__(cls, *args, **kwargs):
            import logging
            import traceback
            fname, line, c, content = traceback.extract_stack(limit=2)[0]
            logging.getLogger('base').warning('kaa.%s has been renamed to kaa.%s and will not be '
                                              'available in kaa.base 1.0:\n%s (%s): %s', 
                                              oldcls, newcls.__name__, fname, line, content)
            # Replace old class with new class object, so we only warn once.
            globals()[oldcls] = newcls
            return newcls(*args, **kwargs)
    return Wrapper

Callback = rename('Callback', Callable)
WeakCallback = rename('WeakCallback', WeakCallable)
InProgressCallback = rename('InProgressCallback', InProgressCallable)
ThreadCallback = rename('ThreadCallback', ThreadCallable)
MainThreadCallback = rename('MainThreadCallback', MainThreadCallable)
NamedThreadCallback = rename('NamedThreadCallback', ThreadPoolCallable)
