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
import math
import tempfile
import distutils.core

# version checking
from version import Version

class Extension(object):
    """
    Extension wrapper with additional functions to find libraries and
    support for config files.
    """
    def __init__(self, output, files, include_dirs=[], library_dirs=[],
                 libraries=[], config=None):
        """
        Init the Extention object.
        """
        self.output = output
        self.files = files
        self.include_dirs = include_dirs
        self.library_dirs = library_dirs
        self.libraries = libraries
        if config:
            self.configfile = os.path.abspath(config)
            # create config file
            open(config, 'w').close()
        else:
            self.configfile = None


    def config(self, line):
        """
        Write a line to the config file.
        """
        if not self.configfile:
            raise AttributeError('No config file defined')
        f = open(self.configfile, 'a')
        f.write(line + '\n')
        f.close()
        
        
    def check_library(self, name, minver):
        """
        Check dependencies add add the flags to include_dirs, library_dirs and
        libraries. The basic logic is taken from pygame.
        """
        try:
            #for parameter in ('version', 'cflags', 'libs'):
            command = name + '-config --version 2>/dev/null'
            version = os.popen(command).read().strip()
            if len(version) == 0:
                raise ValueError, 'command not found'
            if minver and version < minver:
                err= 'requires %s version %s (%s found)' % \
                     (name, minver, version)
                raise ValueError, err

            command = name + '-config --cflags 2>/dev/null'
            for inc in os.popen(command).read().strip().split(' '):
                if inc[2:] and not inc[2:] in self.include_dirs:
                    self.include_dirs.append(inc[2:])
                
            command = name + '-config --libs 2>/dev/null'
            for flag in os.popen(command).read().strip().split(' '):
                if flag[:2] == '-L' and not flag[2:] in self.library_dirs:
                    self.library_dirs.append(flag[2:])
                if flag[:2] == '-l' and not flag[2:] in self.libraries:
                    self.libraries.append(flag[2:])
            return True
        except Exception, e:
            print 'WARNING: "%s-config" failed: %s' % (name, e)
            return False


    def check_cc(self, includes, code, args=''):
        """
        Check the given code with the linker. The optional parameter args
        can contain additional command line options like -l.
        """
        fd, outfile = tempfile.mkstemp()
        os.close(fd)
        f = os.popen("cc -x c - -o %s %s &>/dev/null" % (outfile, args), "w")
        if not f:
            return False
        
        for i in includes:
            f.write('#include %s\n' % i)
        f.write('void main() { ' + code + '};')
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
                                        libraries=self.libraries)

    def __del__(self):
        """
        Delete the config file.
        """
        if self.configfile:
            os.unlink(self.configfile)



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
    if kwargs.has_key('ext_modules'):
        kaa_ext_modules = kwargs['ext_modules']
        ext_modules = []
        for ext in kaa_ext_modules:
            ext_modules.append(ext.convert())
        kwargs['ext_modules'] = ext_modules

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
        f.write('# autogenerated by kaa.base.distribution\n\n')
        f.write('from kaa.base.version import Version\n')
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