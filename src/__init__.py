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

import sys
import os
import imp
import zipimport

# Declare 'kaa' namespace for setuptools. XXX: disabled for now.
try:
    # http://peak.telecommunity.com/DevCenter/setuptools#namespace-packages
    # offers a stern admonition that after declaring a namespace, we must not
    # add any other code to __init__.py.  The reason is that we can't control
    # 
    # However, this isn't possible for us,
    # and, near as I can tell, our approach is safe because kaa sub-modules
    # don't include kaa/__init__.py.  The only module that does is kaa.base.
    # So there's no risk of some other egg getting loaded when we do 'import
    # kaa'.
    #
    # See below for more discussion.
    #
    # This is primarily needed for situations where multiple egg versions
    # are installed.
    #__import__('pkg_resources').declare_namespace('kaa')
    pass
except ImportError:
    # No setuptools installed, no egg support.
    pass


# Import custom logger to update the Python logging module. Unfortunately. we
# can't import this lazy because we add logging.DEBUG2, and that should be
# available immediately after importing kaa.
import logger


# Enable on-demand importing of all modules.  Improves speed of importing kaa
# by almost 50x with warm cache (from 0.065s to 0.0015s) and 325x with cold
# cache (2.6s to 0.008s) on my system.  Although it does of course defer a lot
# of that time to later, it still improves overall performance because it only
# imports the files that actually get used during operation.
#
# It's especially beneficial to reduce import time on systems where any kaa
# module (not just kaa.base) is installed as an egg.  In this case, kaa is
# declared as a namespace package, and (for whatever reason), namespace
# packages get implicitly imported when pkg_resources is imported, which can
# happen when kaa isn't going to be used.
#
# Lazy importing should be completely user-transparent.  See the _LazyProxy
# docstring for more info.
# 
# XXX: recognizing that this is a new feature and possibly (probably :))
# buggy, this constant lets you easily disable this functionality.
ENABLE_LAZY_IMPORTS = 1

def _activate():
    """
    Invoked when the first kaa object is accessed.  Lets us do initial
    bootstrapping, like replace the buggy system os.listdir.
    """
    if sys.hexversion < 0x02060000 and os.name == 'posix':
        # Python 2.5 (all point releases) have a bug with listdir on POSIX
        # systems causing improper out of memory exceptions.  We replace the
        # standard os.listdir with a version from kaa._utils that doesn't have
        # this bug.  Some distros will have patched their 2.5 packages, but
        # since we can't discriminate those, we replace os.listdir regardless.
        #
        # See http://bugs.python.org/issue1608818
        import kaa._utils
        os.listdir = kaa._utils.listdir

    # Kill this function so it only gets invoked once.
    globals()['_activate'] = None


def _lazy_import(mod, names=None):
    """
    If lazy importing is enabled, creates _LazyProxy objects for each name
    specified in the names list and adds it to the global scope.  When
    the _LazyProxy object is accessed, 'mod' gets imported and the global
    name replaced with the actual object from 'mod'.

    If lazy importing is disabled, then names are imported from mod
    immediately, and then added to the global scope.  (It is equivalent
    to 'from mod import <names>')
    """
    if ENABLE_LAZY_IMPORTS:
        # Lazy importing is enabled, so created _LazyProxy classes.
        if names:
            # from mod import <names>
            for name in names:
                lazy = _LazyProxy(name, (__builtins__['object'],), {'_mod': mod, '_name': name, '_names': names})
                globals()[name] = lazy
        else:
            # import mod
            globals()[mod] = _LazyProxy(mod, (__builtins__['object'],), {'_mod': mod})
    else:
        # No lazy importing, import everything immediately.
        if globals()['_activate']:
            globals()['_activate']()
        omod = __import__(mod, globals(), fromlist=names)
        if names:
            # from mod import <names>
            for name in names:
                globals()[name] = getattr(omod, name)
        else:
            # import mod
            globals()[mod] = omod


class _LazyProxy(type):
    """
    Metaclass used to construct individual proxy classes for all names within
    the kaa namespace.  When the proxy class for a given name is accessed in
    any meaningful way the underlying module is imported and the name from
    that module replaces the _LazyProxy in the kaa namespace.

    By "meaninful" access, in each of the following code snippets, behaviour
    is as if the underlying module had been imported all along:

        # imports callable (repr() hook)
        >>> print kaa.Callable

        # imports process (dir() hook, but python 2.6 only; python 2.5 will
        # still automatically import, but dir() returns [])
        >>> dir(kaa.Process)

        # imports io (deep metaclass magic)
        >>> class MyIO(kaa.IOMonitor):
        ...    pass

        # imports io and callable (MI is supported)
        >>> class MyIO(kaa.IOMonitor, kaa.Callable):
        ...     pass

        # imports coroutine (== hook)
        >>> print policy == kaa.POLICY_PASS_LAST

        # imports main
        >>> kaa.main.run()

        # imports thread
        >>> @kaa.threaded()
        ... def foo():
        ...     pass

        # imports timer; this works, but it's suboptimal because it means the
        # user is _always_ interfacing through a proxy object.
        >>> from kaa import timed
        >>> @timed(1.0)
        ... def foo():
        ...     pass
    """
    def __new__(cls, name, bases, dict):
        if bases == (__builtins__['object'],):
            # called by _lazy_import(), create a new LazyProxy class for the
            # given module/name, which is defined in dict.
            return type.__new__(cls, name, (__builtins__['object'],), dict)
        else:
            # called when something tries to subclass a LazyProxy.  Replace all
            # LazyProxy bases with the actual object (importing as needed) and
            # construct the new class subclassed from the newly imported kaa
            # objects.
            bases = ((b.__get() if type(b) == _LazyProxy else b) for b in bases)
            return type(name, tuple(bases), dict)


    def __get(cls):
        """
        Returns the underlying proxied object, importing the module if necessary.
        """
        try:
            return type.__getattribute__(cls, '_obj')
        except AttributeError:
            pass

        if globals()['_activate']:
            # First kaa module loaded, invoke _activate()
            globals()['_activate']()

        mod = type.__getattribute__(cls, '_mod')
        try:
            names = type.__getattribute__(cls, '_names')
        except AttributeError:
            names = []

        # Keep a copy of the current global scope, see later for why.
        before = globals().copy()
        # Load the module and pull in the specified names.
        imp.acquire_lock()
        omod = __import__(mod, globals(), fromlist=names)
        imp.release_lock()

        if not names:
            # Proxying whole module.
            globals()[mod] = omod
            cls._obj = omod
            return omod
        else:
            # Kludge: if we import a module with the same name as an existing
            # global (e.g.  coroutine, generator, signals), the module will
            # replace the _LazyProxy.  If a previous _LazyProxy has now been
            # replaced by a module, restore the original _LazyProxy.
            for key in before:
                if type(before[key]) == _LazyProxy and type(globals().get(key)).__name__ == 'module':
                    globals()[key] = before[key]

            # Replace the _LazyProxy objects with the actual module attributes.
            for n in names:
                globals()[n] = getattr(omod, n)
            name = type.__getattribute__(cls, '_name')
            obj = getattr(omod, name)
            # Need to wrap obj in staticmethod or else it becomes an unbound class method.
            cls._obj = staticmethod(obj)
            return obj


    def __getattribute__(cls, attr):
        # __get gets mangled
        if attr == '_LazyProxy__get':
            return type.__getattribute__(cls, attr)
        return getattr(cls.__get(), attr)

    def __getitem__(cls, item):
        return cls.__get()[item]

    def __setitem__(cls, item, value):
        cls.__get()[item] = value

    def __call__(cls, *args, **kwargs):
        return cls.__get()(*args, **kwargs)

    def __repr__(cls):
        return repr(cls.__get())

    def __dir__(cls):
        # Python 2.6 only
        return dir(cls.__get())

    def __eq__(cls, other):
        return cls.__get() == other


# Base object class for all kaa classes
_lazy_import('object', ['Object'])

# Callable classes
_lazy_import('callable', ['Callable', 'WeakCallable', 'CallableError'])

# Notifier-aware callbacks do not need to be exported outside kaa.base
# _lazy_import('nf_wrapper', ['NotifierCallback', 'WeakNotifierCallback'])

# Signal and dict of Signals
_lazy_import('signals', ['Signal', 'Signals'])

# Async programming classes, namely InProgress
_lazy_import('async', [
    'TimeoutException', 'InProgress', 'InProgressCallable', 'InProgressAny',
    'InProgressAll', 'InProgressAborted', 'InProgressStatus', 'inprogress',
    'delay'
])

# Thread callables, helper functions and decorators
_lazy_import('thread', [
    'MainThreadCallable', 'ThreadPoolCallable', 'ThreadCallable',
    'is_mainthread', 'threaded', 'synchronized', 'MAINTHREAD',
    'ThreadInProgress', 'ThreadPool', 'register_thread_pool', 'get_thread_pool'
])

# Timer classes and decorators
_lazy_import('timer', [
    'Timer', 'WeakTimer', 'OneShotTimer', 'WeakOneShotTimer', 'AtTimer',
    'OneShotAtTimer', 'timed', 'POLICY_ONCE', 'POLICY_MANY', 'POLICY_RESTART'
])

# IO/Socket handling
_lazy_import('io', ['IOMonitor', 'WeakIOMonitor', 'IO_READ', 'IO_WRITE', 'IOChannel'])
_lazy_import('sockets', ['Socket', 'SocketError'])

# Event and event handler classes
_lazy_import('event', ['Event', 'EventHandler', 'WeakEventHandler'])

# coroutine decorator and helper classes
_lazy_import('coroutine', [
    'NotFinished', 'coroutine', 'POLICY_SYNCHRONIZED', 'POLICY_SINGLETON',
    'POLICY_PASS_LAST'
])

# generator support
_lazy_import('generator', ['Generator', 'generator'])

# process management
_lazy_import('process', ['Process'])

# special gobject thread support
_lazy_import('gobject', ['GOBJECT', 'gobject_set_threaded'])

# Import the two important strutils functions
_lazy_import('strutils', ['str_to_unicode', 'unicode_to_str'])

# Add tempfile support.
_lazy_import('utils', ['tempfile'])

# Expose main loop functions under kaa.main
_lazy_import('main')
_lazy_import('main', ['signals'])



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
#   4. kaa.base as source tree, kaa.foo as source tree; this should be easiest
#      as the import hooks are basically bypassed.
#
# Some other uncommon but possible scenarios involving multiple versions we
# should consider.  We should prefer eggs in these cases:
#
#   5. kaa.base as source tree AND egg; ensure that 'kaa' and e.g. 'kaa.rpc'
#      come from the same module.
#
# If kaa.foo exists as both an on-disk tree and an egg, the egg will be preferred.
# However, if kaa.base exists as both, we can't easily control which one gets
# loaded.  In this case we should print a warning.
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

        imp.acquire_lock()
        try:
            mod = imp.load_module(name, *self._info)
        finally:
            if self._info[0]:
                self._info[0].close()
            imp.release_lock()
        return mod
        

class KaaFinder(__builtins__['object']):
    def __init__(self):
        self.warn_on_mixed = True
        # Discover kaa eggs
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

        if len(path) > 1 and any('.egg/' not in p for p in path) and self.warn_on_mixed:
            # This probably isn't what the user wants.  At any rate we can't easily
            # control which one to use.
            print('WARNING: Multiple and mixed (egg and non-egg) versions of kaa.base installed.\n'
                  '         This MIGHT appear to mostly work, but this configuration is not supported.')
            # Just spam the warning once.
            self.warn_on_mixed = False

        if name not in self.kaa_eggs or os.path.isdir(self.kaa_eggs[name]):
            # There's no egg, or the egg is actually uncompressed as an
            # on-disk tree (i.e. kaa_foo.egg is actually a directory).
            imp.acquire_lock()
            # problem: kaa.base tree, kaa.foo egg
            try:
                searches = (
                    # Relative import of submodule (strip kaa.) from given path
                    lambda: imp.find_module(name[4:], path),
                    # Absolute import from given path
                    lambda: imp.find_module(name, path),
                    # Check sys.path for the given name.  (kaa.base tree, kaa.foo egg)
                    lambda: imp.find_module(name, sys.path),
                    # Check for kaa/foo in sys.path (kaa.base egg, kaa.foo tree)
                    lambda: imp.find_module(name.replace('.', '/'), sys.path)
                )
                for doimp in searches:
                    try:
                        info = doimp()
                        break
                    except ImportError:
                        pass
                else:
                    return
            finally:
                imp.release_lock()

            return KaaLoader(info)

        # Egg is available for requested module, so attempt to import it.
        imp.acquire_lock()
        try:
            o = zipimport.zipimporter(self.kaa_eggs[name] + '/kaa')
        finally:
            imp.release_lock()
        return o

# Now install our custom hooks.  Remove any existing KaaFinder import hooks, which
# could exist from other versions of kaa.base being imported by pkg_resources,
# or perhaps kaa was reload()ed.
if '.egg/' in __file__:
    [sys.meta_path.remove(x) for x in sys.meta_path if type(x).__name__ == 'KaaFinder']
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
