# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# utils.py - Miscellaneous system utilities
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# Copyright (C) 2006 Dirk Meyer, Jason Tackaberry
#
# First Edition: Jason Tackaberry <tack@urandom.ca>
# Maintainer:    Jason Tackaberry <tack@urandom.ca>
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

__all__ = [ ]

import sys
import os
import stat
import time
import imp
import logging
import inspect
import re

import kaa
import _utils

# get logging object
log = logging.getLogger('kaa')


def which(file, path = None):
    """
    Does what which(1) does: searches the PATH for a given file
    name and returns a list of matches.
    """
    if not path:
        path = os.getenv("PATH")

    for p in path.split(":"):
        fullpath = os.path.join(p, file)
        try:
            st = os.stat(fullpath)
        except OSError:
            continue

        if os.geteuid() == st[stat.ST_UID]:
            mask = stat.S_IXUSR
        elif st[stat.ST_GID] in os.getgroups():
            mask = stat.S_IXGRP
        else:
            mask = stat.S_IXOTH

        if stat.S_IMODE(st[stat.ST_MODE]) & mask:
            return fullpath

    return None


class Lock(object):
    def __init__(self):
        self._read, self._write = os.pipe()

    def release(self, exitcode):
        os.write(self._write, str(exitcode))
        os.close(self._read)
        os.close(self._write)

    def wait(self):
        exitcode = os.read(self._read, 1)
        os.close(self._read)
        os.close(self._write)
        return int(exitcode)

    def ignore(self):
        os.close(self._read)
        os.close(self._write)


def daemonize(stdin = '/dev/null', stdout = '/dev/null', stderr = None,
              pidfile=None, exit = True, wait = False):
    """
    Does a double-fork to daemonize the current process using the technique
    described at http://www.erlenstar.demon.co.uk/unix/faq_2.html#SEC16 .

    If exit is True (default), parent exits immediately.  If false, caller will receive
    the pid of the forked child.
    """

    lock = 0
    if wait:
        lock = Lock()

    # First fork.
    try:
        pid = os.fork()
        if pid > 0:
            if wait:
                exitcode = lock.wait()
                if exitcode:
                    sys.exit(exitcode)
            if exit:
                # Exit from the first parent.
                sys.exit(0)

            # Wait for child to fork again (otherwise we have a zombie)
            os.waitpid(pid, 0)
            return pid
    except OSError, e:
        log.error("Initial daemonize fork failed: %d, %s\n", e.errno, e.strerror)
        sys.exit(1)

    os.chdir("/")
    os.setsid()

    # Second fork.
    try:
        pid = os.fork()
        if pid > 0:
            # Exit from the second parent.
            sys.exit(0)
    except OSError, e:
        log.error("Second daemonize fork failed: %d, %s\n", e.errno, e.strerror)
        sys.exit(1)

    # Create new standard file descriptors.
    if not stderr:
        stderr = stdout
    stdin = file(stdin, 'r')
    stdout = file(stdout, 'a+')
    stderr = file(stderr, 'a+', 0)
    if pidfile:
        file(pidfile, 'w+').write("%d\n" % os.getpid())

    # Remap standard fds.
    os.dup2(stdin.fileno(), sys.stdin.fileno())
    os.dup2(stdout.fileno(), sys.stdout.fileno())
    os.dup2(stderr.fileno(), sys.stderr.fileno())

    # Replace any existing thread notifier pipe, otherwise we'll be listening
    # to our parent's thread notifier.
    from kaa.notifier.thread import create_thread_notifier_pipe
    create_thread_notifier_pipe(new=False, purge=True)

    return lock


def is_running(name):
    """
    Check if the program with the given name is running. The program
    must have called set_running itself. Returns the pid or 0.
    """
    if not os.path.isfile(kaa.tempfile('run/' + name)):
        return 0
    run = open(kaa.tempfile('run/' + name))
    pid = run.readline().strip()
    cmdline = run.readline()
    run.close()
    if not os.path.exists('/proc/%s/cmdline' % pid):
        return 0
    current = open('/proc/%s/cmdline' % pid).readline()
    if current == cmdline or current.strip('\x00') == name:
        return int(pid)
    return 0


def set_running(name, modify = True):
    """
    Set this program as running with the given name.  If modify is True,
    the process name is updated as described in set_process_name().
    """
    cmdline = open('/proc/%s/cmdline' % os.getpid()).readline()
    run = open(kaa.tempfile('run/' + name), 'w')
    run.write(str(os.getpid()) + '\n')
    run.write(cmdline)
    run.close()
    if modify:
        _utils.set_process_name(name, len(cmdline))


def set_process_name(name):
    """
    On Linux systems later than 2.6.9, this function sets the process name as it
    appears in ps, and so that it can be found with killall.

    Note: name will be truncated to the cumulative length of the original
    process name and all its arguments; once updated, passed arguments will no
    longer be visible.
    """
    cmdline = open('/proc/%s/cmdline' % os.getpid()).readline()
    _utils.set_process_name(name, len(cmdline))


def get_num_cpus():
    """
    Returns the number of processors on the system, or raises RuntimeError
    if that value cannot be determined.
    """
    try:
        if sys.platform == 'win32':
            return int(os.environ['NUMBER_OF_PROCESSORS'])
        elif sys.platform == 'darwin':
            return int(os.popen('sysctl -n hw.ncpu').read())
        else:
            return os.sysconf('SC_NPROCESSORS_ONLN')
    except (KeyError, ValueError, OSError, AttributeError):
        pass

    raise RuntimeError('Could not determine number of processors')


def get_plugins(path, include_files=True, include_directories=True):
    """
    Get a list of plugins in the given plugin directory. The 'path' argument
    can also be a full path of an __init__ file.
    """
    if os.path.isfile(path):
        path = os.path.dirname(path)
    result = []
    for plugin in os.listdir(path):
        for ext in ('.py', '.pyc', '.pyo'):
            if plugin.endswith(ext) and include_files:
                plugin = plugin[:-len(ext)]
                break
        else:
            if not include_directories or not os.path.isdir(os.path.join(path, plugin)):
                continue
        if not plugin in result and not plugin == '__init__' and \
               not plugin.startswith('.'):
            result.append(plugin)
    return result


class Singleton(object):
    """
    Create Singleton object from classref on demand.
    """

    class MemberFunction(object):
        def __init__(self, singleton, name):
            self._singleton = singleton
            self._name = name

        def __call__(self, *args, **kwargs):
            return getattr(self._singleton(), self._name)(*args, **kwargs)


    def __init__(self, classref):
        self._singleton = None
        self._class = classref

    def __call__(self):
        if self._singleton is None:
            self._singleton = self._class()
        return self._singleton

    def __getattr__(self, attr):
        if self._singleton is None:
            return Singleton.MemberFunction(self, attr)
        return getattr(self._singleton, attr)


class property(property):
    """
    Replaces built-in property function to extend it as per
    http://bugs.python.org/issue1416
    """
    def __init__(self, fget = None, fset = None, fdel = None, doc = None):
        super(property, self).__init__(fget, fset, fdel)
        self.__doc__ = doc or fget.__doc__

    def _add_doc(self, prop, doc = None):
        prop.__doc__ = doc or self.__doc__
        return prop

    def setter(self, fset):
        if isinstance(fset, property):
            # Wrapping another property, use deleter.
            self, fset = fset, fset.fdel
        return self._add_doc(property(self.fget, fset, self.fdel))

    def deleter(self, fdel):
        if isinstance(fdel, property):
            # Wrapping another property, use setter.
            self, fdel = fdel, fdel.fset
        return self._add_doc(property(self.fget, self.fset, fdel))

    def getter(self, fget):
        return self._add_doc(property(fget, self.fset, self.fdel), fget.__doc__ or self.fget.__doc__)


def sysimport(name):
    """
    Help to import modules with name conflict. E.g. thread.py in notifier
    uses sysimport('thread').
    """
    # Fast path: see if the module has already been imported.
    try:
        return sys.modules[name]
    except KeyError:
        pass

    # Remove the current directory and anything below it from the
    # search path.
    cwd = os.path.realpath(os.getcwd())
    path = [ x for x in sys.path if x and not os.path.realpath(x).startswith(cwd) ]
    fp, pathname, description = imp.find_module(name, path)
    try:
        return imp.load_module(name, fp, pathname, description)
    finally:
        # Since we may exit via an exception, close fp explicitly.
        if fp:
            fp.close()


try:
    from functools import update_wrapper
except ImportError:
    # update_wrapper is only available in 2.5+, so create our own for
    # later versions of Python.
    def update_wrapper(wrapper, wrapped):
        for attr in ('__module__', '__name__', '__doc__'):
            setattr(wrapper, attr, getattr(wrapped, attr))
        wrapper.__dict__.update(wrapped.__dict__)


def wraps(origfunc, lshift=0):
    """
    Decorator factory: used to create a decorator that assumes the same
    attributes (name, docstring, signature) as its decorated function.
    Preserving the function signature and docstring is particularly necessary
    for documentation generators (such as epydoc) that use introspection to
    construct the doc.

    This logic is inspired from Michele Simionato's decorator module.

        >>> def decorator(func):
        ...     @wraps(func)
        ...     def newfunc(*args, **kwargs):
        ...             # custom logic here ...
        ...             return func(*args, **kwargs)
        ...     return newfunc

    @param origfunc: the original function being decorated which is to be
        wrapped.
    @param lshift: number of arguments to shift from the left of the original
        function's call spec.  Wrapped function will have this nubmer of
        arguments removed.
    @return: a decorator which has the attributes of the decorated function.
    """
    # The idea here is to turn an origfunc with a signature like:
    #    origfunc(a, b, c=42, *args, **kwargs)
    # into:
    #    lambda a, b, c=42, *args, **kwargs: func(a, b, c=c, *args, **kwargs)
    spec = list(inspect.getargspec(origfunc))

    # Wrapped function may need different callspec.  Currently we can just
    # shift from the left of the args (e.g. for kaa.threaded progress arg).
    # FIXME: doesn't work if the shifted arg is a kwarg.
    if lshift:
        spec[0] = spec[0][lshift:]

    if spec[-1]:
        # For the lambda signature's kwarg defaults, remap them into values
        # that can be referenced from the eval's local scope.  Otherwise only
        # intrinsics could be used as kwarg defaults.
        # Preserve old kwarg value list, to be passed into eval's locals scope.
        kwarg_values = spec[-1]
        # Changes (a=1, b=Foo) to a='__kaa_kw_defs[1]', b='__kaa_kw_defs[2]'
        sigspec = spec[:3] + [[ '__kaa_kw_defs[%d]' % n for n in range(len(spec[-1])) ]]
        sig = inspect.formatargspec(*sigspec)[1:-1]
        # Removes the quotes between __kaa_kw_defs[x]
        sig = re.sub(r"'(__kaa_kw_defs\[\d+\])'", '\\1', sig)

        # For the call spec, change defaults from the kwarg defaults to
        # the name of the kwarg.  e.g. c=42 in the argspec will be translated
        # to c=c in the callspec.  We still want these args to be kwargs,
        # but don't want to override the value passed in the call.
        spec = spec[:3] + [spec[0][-len(spec[3]):]]
        callspec = inspect.formatargspec(formatvalue=lambda v: '=%s' % v, *spec)[1:-1]
    else:
        sig = callspec = inspect.formatargspec(*spec)[1:-1]
        kwarg_values = None

    src = 'lambda %s: __kaa_call_(%s)' % (sig, callspec)

    def decorator(func):
        dec_func = eval(src, {'__kaa_call_': func, '__kaa_kw_defs': kwarg_values})
        return update_wrapper(dec_func, origfunc)
    return decorator


class DecoratorDataStore(object):
    """
    A utility class for decorators that sets or gets a value to/from a
    decorated function.  Attributes of instances of this class can be get, set,
    or deleted, and those attributes are associated with the decorated
    function.

    The object to which the data is attached is either the function itself for
    non-method, or the instance object for methods.

    There are two possible perspectives of using the data store: from inside
    the decorator, and from outside the decorator.  This allows, for example, a
    method to access data stored by one of its decorators.
    """
    def __init__(self, func, newfunc=None, newfunc_args=None):
        # Object the data will be stored in.
        target = func
        if hasattr(func, 'im_self'):
            # Data store requested for a specific method.
            target = func.im_self

        # This kludge compares the code object of newfunc (this wrapper) with the
        # code object of the first argument's attribute of the function's name.  If
        # they're the same, then we must be decorating a method, and we can attach
        # the timer object to the instance instead of the function.
        method = newfunc_args and getattr(newfunc_args[0], func.func_name, None)
        if method and newfunc.func_code == method.func_code:
            # Decorated function is a method, so store data in the instance.
            target = newfunc_args[0]

        self.__target = target
        self.__name = func.func_name

    def __hash(self, key):
        return '__kaa_decorator_data_%s_%s' % (key, self.__name)

    def __getattr__(self, key):
        if key.startswith('_DecoratorDataStore__'):
            return super(DecoratorDataStore, self).__getattr__(key)
        return getattr(self.__target, self.__hash(key))

    def __setattr__(self, key, value):
        if key.startswith('_DecoratorDataStore__'):
            return super(DecoratorDataStore, self).__setattr__(key, value)
        return setattr(self.__target, self.__hash(key), value)

    def __hasattr__(self, key):
        return hasattr(self.__target, self.__hash(key))

    def __contains__(self, key):
        return hasattr(self.__target, self.__hash(key))

    def __delattr__(self, key):
        return delattr(self.__target, self.__hash(key))

def utc2localtime(t):
    """
    Transform given seconds from UTC into localtime
    """
    if not t:
        # no time value given
        return 0
    if time.daylight:
        return t - time.altzone
    else:
        return t - time.timezone

def localtime2utc(t):
    """
    Transform given seconds from localtime into UTC
    """
    if not t:
        # no time value given
        return 0
    if time.daylight:
        return t + time.altzone
    else:
        return t + time.timezone


def utctime():
    """
    Return current time in seconds in UTC
    """
    return int(localtime2utc(time.time()))

