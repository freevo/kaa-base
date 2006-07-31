# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# distribution.py - distutils functions for kaa packages
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# Copyright (C) 2005 Dirk Meyer, Jason Tackaberry
#
# First Edition: Dirk Meyer <dmeyer@tzi.de>
# Maintainer:    Dirk Meyer <dmeyer@tzi.de>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of MER-
# CHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General
# Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA
#
# -----------------------------------------------------------------------------

# python imports
import os
import sys
import math
import stat
import re
import tempfile
import distutils.core

# version checking
from version import Version

_libraries = []

class Library(object):
    def __init__(self, name):
        self.name = name
        self.include_dirs = []
        self.library_dirs = []
        self.libraries = []
        self.valid = False

    
    def check(self, minver):
        """
        Check dependencies add add the flags to include_dirs, library_dirs and
        libraries. The basic logic is taken from pygame.
        """
        print 'checking for', self.name, '>=', minver, '...',
        sys.__stdout__.flush()

        if os.system("%s-config --version &>/dev/null" % self.name) == 0:
            # Use foo-config if it exists.
            command = "%s-config %%s 2>/dev/null" % self.name
            version_arg = "--version"
        elif os.system("pkg-config %s --exists &>/dev/null" % self.name) == 0:
            # Otherwise try pkg-config foo.
            command = "pkg-config %s %%s 2>/dev/null" % self.name
            version_arg = "--modversion"
        else:
            print 'no'
            return False

        version = os.popen(command % version_arg).read().strip()
        if len(version) == 0:
            print 'no'
            return False
        if minver and version < minver:
            print 'no (%s)' % version
            return False

        for inc in os.popen(command % "--cflags").read().strip().split(' '):
            if inc[2:] and not inc[2:] in self.include_dirs:
                self.include_dirs.append(inc[2:])

        for flag in os.popen(command % "--libs").read().strip().split(' '):
            if flag[:2] == '-L' and not flag[2:] in self.library_dirs:
                self.library_dirs.append(flag[2:])
            if flag[:2] == '-l' and not flag[2:] in self.libraries:
                self.libraries.append(flag[2:])
        print version
        self.valid = True
        return True

    def compile(self, includes, code, args=''):
        print 'checking for', self.name, '...',
        fd, outfile = tempfile.mkstemp()
        os.close(fd)
        f = os.popen("cc -x c - -o %s %s 2>/dev/null >/dev/null" % (outfile, args), "w")
        if not f:
            print 'failed'
            return False
        
        for i in includes:
            f.write('#include %s\n' % i)
        f.write('int main() { ' + code + '\nreturn 0;\n};')
        result = f.close()

        if os.path.exists(outfile):
            os.unlink(outfile)

        if result == None:
            print 'ok'
            self.valid = True
            return True
        print 'no'
        return False

        
def check_library(name, *args):
    lib = Library(name)
    if len(args) < 2:
        lib.check(args[0])
    else:
        lib.compile(*args)
    _libraries.append(lib)
    return lib


def get_library(name):
    for l in _libraries:
        if l.name == name and l.valid:
            return l
    return None

class Configfile(object):
    """
    Config file for the build process.
    """
    def __init__(self, filename):
        self.file = os.path.abspath(filename)
        # create config file
        open(self.file, 'w').close()


    def append(self, line):
        """
        Append something to the config file.
        """
        f = open(self.file, 'a')
        f.write(line + '\n')
        f.close()


    def define(self, variable, value=None):
        """
        Set a #define.
        """
        if value == None:
            self.append('#define %s' % variable)
        else:
            self.append('#define %s %s' % (variable, value))

            
    def unlink(self):
        """
        Delete config file.
        """
        os.unlink(self.file)

        
class Extension(object):
    """
    Extension wrapper with additional functions to find libraries and
    support for config files.
    """
    def __init__(self, output, files, include_dirs=[], library_dirs=[], 
                 libraries=[], extra_compile_args = [], config=None):
        """
        Init the Extention object.
        """
        self.output = output
        self.files = files
        self.include_dirs = include_dirs[:]
        self.library_dirs = library_dirs[:]
        self.libraries = libraries[:]
        self.extra_compile_args = ["-Wall"] + extra_compile_args
        if config:
            self.configfile = Configfile(config)
        else:
            self.configfile = None


    def config(self, line):
        """
        Write a line to the config file.
        """
        if not self.configfile:
            raise AttributeError('No config file defined')
        self.configfile.append(line)
        
        
    def add_library(self, name):
        """
        """
        for l in _libraries:
            if l.name == name and l.valid:
                for attr in ('include_dirs', 'library_dirs', 'libraries'):
                    for val in getattr(l, attr):
                        if not val in getattr(self, attr):
                            getattr(self, attr).append(val)
                return True
        return False


    def check_library(self, name, minver):
        """
        Check dependencies add add the flags to include_dirs, library_dirs and
        libraries. The basic logic is taken from pygame.
        """
        try:
            if os.system("pkg-config %s --exists &>/dev/null" % name) == 0:
                # Use pkg-config (it also wraps foo-config)
                command = "pkg-config %s %%s 2>/dev/null" % name
                if minver:
                    if not os.system(command % '--atleast-version %s' % minver) == 0:
                        err= 'requires %s version %s' % (name, minver)
                        raise ValueError, err
            elif os.system("%s-config --version &>/dev/null" % name) == 0:
                # Use foo-config if it exists.
                command = "%s-config %%s 2>/dev/null" % name
                version = os.popen(command % '--version').read().strip()
                if len(version) == 0:
                    raise ValueError, 'command not found'
                # this check may be wrong, but it works if wrapped with
                # pkg-config. Maybe always use pkg-config?
                if minver and version < minver:
                    err= 'requires %s version %s (%s found)' % \
                         (name, minver, version)
                    raise ValueError, err
            else:
                raise ValueError, "%s is not installed" % name

            for inc in os.popen(command % "--cflags").read().strip().split(' '):
                if inc[2:] and not inc[2:] in self.include_dirs:
                    self.include_dirs.append(inc[2:])
                
            for flag in os.popen(command % "--libs").read().strip().split(' '):
                if flag[:2] == '-L' and not flag[2:] in self.library_dirs:
                    self.library_dirs.append(flag[2:])
                if flag[:2] == '-l' and not flag[2:] in self.libraries:
                    self.libraries.append(flag[2:])
            return True
        except Exception, e:
            self.error = e
            return False


    def check_cc(self, includes, code, args=''):
        """
        Check the given code with the linker. The optional parameter args
        can contain additional command line options like -l.
        """
        fd, outfile = tempfile.mkstemp()
        os.close(fd)
        f = os.popen("cc -x c - -o %s %s 2>/dev/null >/dev/null" % (outfile, args), "w")
        if not f:
            return False
        
        for i in includes:
            f.write('#include %s\n' % i)
        f.write('int main() { ' + code + '\nreturn 0;\n};')
        result = f.close()
        
        if os.path.exists(outfile):
            os.unlink(outfile)

        return result == None


    def convert(self):
        """
        Convert Extension into a distutils.core.Extension.
        """
        return distutils.core.Extension(self.output, self.files,
                                        library_dirs=self.library_dirs,
                                        include_dirs=self.include_dirs,
                                        libraries=self.libraries,
                                        extra_compile_args=self.extra_compile_args)

    def __del__(self):
        """
        Delete the config file.
        """
        if self.configfile:
            self.configfile.unlink()


class EmptyExtensionsList(list):
    """
    A list that is non-zero even when empty.  Used for the ext_modules
    kwarg in setup() for modules with no ext_modules.

    This is a kludge to solve a peculiar problem.  On architectures like
    x86_64, distutils will install "pure" modules (i.e. no C extensions)
    under /usr/lib, and platform-specific modules (with extensions) under
    /usr/lib64.  This is a problem for kaa, because with kaa we have a single
    namespace (kaa/) that have several independent modules: that is, each
    module in Kaa can be installed separately, but they coexist under the
    kaa/ directory hierarchy.

    On x86_64, this results in some kaa modules being installed in /usr/lib
    and others installed in /usr/lib64.  The first problem is that 
    kaa/__init__.py is provided by kaa.base, so if kaa.base is installed
    in /usr/lib/ then /usr/lib64/python*/site-packages/kaa/__init__.py does
    not exist and therefore we can't import any modules from that.  We could
    drop a dummy __init__.py there, but then python will have two valid kaa
    modules and only ever see one of them, the other will be ignored.

    So this kludge makes distutils always think the module has extensions,
    so it will install in the platform-specific libdir.  As a result, on
    x86_64, all kaa modules will be installed in /usr/lib64, which is what
    we want.
    """
    def __nonzero__(self):
        return True

        

def setup(**kwargs):
    """
    A setup script wrapper for kaa modules.
    """
    def _find_packages(kwargs, dirname, files):
        """
        Helper function to create 'packages' and 'package_dir'.
        """
        if not '__init__.py' in files:
            return
        python_dirname = 'kaa.' + kwargs['module'] + \
                         dirname[3:].replace('/', '.')
        kwargs['package_dir'][python_dirname] = dirname
        kwargs['packages'].append(python_dirname)

    
    if not kwargs.has_key('module'):
        raise AttributeError('\'module\' not defined')

    # create name
    kwargs['name'] = 'kaa-' + kwargs['module']

    # search for source files and add it package_dir and packages
    kwargs['package_dir'] = {}
    kwargs['packages']    = []
    os.path.walk('src', _find_packages, kwargs)

    # delete 'module' information, not used by distutils.setup
    del kwargs['module']

    # convert Extensions
    if kwargs.get('ext_modules'):
        kaa_ext_modules = kwargs['ext_modules']
        ext_modules = []
        for ext in kaa_ext_modules:
            ext_modules.append(ext.convert())
        kwargs['ext_modules'] = ext_modules
    else:
        # No extensions, but trick distutils into thinking we do have, so
        # the module gets installed in the platform-specific libdir.
        kwargs['ext_modules'] = EmptyExtensionsList()

    # check version.py information
    write_version = False
    if kwargs.has_key('version'):
        write_version = True
        # check if a version.py is there
        if os.path.isfile('src/version.py'):
            # read the file to find the old version information
            f = open('src/version.py')
            for line in f.readlines():
                if line.startswith('VERSION'):
                    if eval(line[10:-1]) == kwargs['version']:
                        write_version = False
                    break
            f.close()

    if write_version:
        # Write a version.py and add it to the list of files to
        # be installed.
        f = open('src/version.py', 'w')
        f.write('# version information for %s\n' % kwargs['name'])
        f.write('# autogenerated by kaa.distribution\n\n')
        f.write('from kaa.version import Version\n')
        f.write('VERSION = Version(\'%s\')\n' % kwargs['version'])
        f.close()

    # add some missing keywords
    if not kwargs.has_key('author'):
        kwargs['author'] = 'Freevo Development Team'
    if not kwargs.has_key('author_email'):
        kwargs['author_email'] = 'freevo-devel@lists.sourceforge.net'
    if not kwargs.has_key('url'):
        kwargs['url'] = 'http://freevo.sourceforge.net/kaa'

    # run the distutils.setup function
    return distutils.core.setup(**kwargs)
