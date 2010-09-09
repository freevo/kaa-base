# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# build_py.py - kaa.config cxml install support
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# Copyright 2006-2009 Dirk Meyer, Jason Tackaberry
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

# python imports
from __future__ import absolute_import
import os
import sys
import glob
import types
import stat
import re
import fnmatch

try:
    from distutils.command.build_py import build_py_2to3 as distutils_build_py
except ImportError:
    from distutils.command.build_py import build_py as distutils_build_py

from . import xmlconfig

kaa_module_bootstrap = '''\
# This is an auto-generated file.  Package maintainers: please ensure this
# file is packaged only with the kaa-base package if you are not packaging
# eggs.
try:
    try:
        __import__('pkg_resources').declare_namespace('kaa')
        __import__('pkg_resources').get_distribution('kaa-base').activate()
    except __import__('pkg_resources').DistributionNotFound:
        # kaa.base not yet installed
        pass
except ImportError:
    # setuptools not installed
    pass
from kaa.base import *
'''

class build_py(distutils_build_py):

    kaa_compiler = {
        'cxml': xmlconfig.convert
    }
    opts_2to3 = {}

    def kaa_compile_extras(self, module, module_file, package):
        if isinstance(package, str):
            package = package.split('.')
        elif isinstance(package, (list, tuple)):
            raise TypeError("'package' must be a string (dot-separated), list, or tuple")
        ttype = os.path.splitext(module_file)[1][1:]
        outfile = self.get_module_outfile(self.build_lib, package, module)
        tmpfile = outfile[:-2] + ttype
        if os.path.isfile(outfile) and \
               os.stat(module_file)[stat.ST_MTIME] < os.stat(outfile)[stat.ST_MTIME]:
            # template up-to-date
            return
        self.copy_file(module_file, tmpfile, preserve_mode=0)
        print('convert %s -> %s' % (tmpfile, tmpfile[:-len(ttype)] + 'py'))
        self.kaa_compiler[ttype](tmpfile, tmpfile[:-len(ttype)] + 'py', '.'.join(package))
        os.unlink(tmpfile)


    def check_package (self, package, package_dir):
        if package.endswith('plugins'):
            return None
        return distutils_build_py.check_package(self, package, package_dir)


    def build_packages (self):
        distutils_build_py.build_packages(self)
        if sys.modules.get('setuptools') or 'kaa.base' in self.package_dir:
            open('%s/kaa/__init__.py' % self.build_lib, 'w').write(kaa_module_bootstrap)
        elif os.path.isfile('%s/kaa/__init__.py' % self.build_lib):
            os.unlink('%s/kaa/__init__.py' % self.build_lib)
        for package in self.packages:
            package_dir = self.get_package_dir(package)
            for ext in self.kaa_compiler.keys():
                for f in glob.glob(os.path.join(package_dir, "*." + ext)):
                    module_file = os.path.abspath(f)
                    module = os.path.splitext(os.path.basename(f))[0]
                    self.kaa_compile_extras(module, module_file, package)

    def run_2to3(self, files):
        excludes = build_py.opts_2to3.get('exclude')
        nofix = build_py.opts_2to3.get('nofix')
        groups = {'all': files}
        for file in files[:]:
            # Strip 'build/lib.*/kaa/module/' from name.
            relfile = re.sub(r'build\/[^/]*\/kaa\/[^/]+\/', '', file)
            if excludes:
                for pattern in excludes:
                    if fnmatch.fnmatch(relfile, pattern):
                        files.remove(file)
            if nofix:
                for pattern, fixers in nofix.items():
                    if fnmatch.fnmatch(relfile, pattern) and file in files:
                        groups.setdefault(tuple(fixers), []).append(file)
                        files.remove(file)

        from lib2to3.refactor import get_fixers_from_package
        all_fixers = set(get_fixers_from_package('lib2to3.fixes'))
        print(all_fixers)
        for fixers, files in groups.items():
            if not files:
                continue
            if fixers == 'all':
                self.fixer_names = all_fixers
            else:
                self.fixer_names = all_fixers.difference('lib2to3.fixes.fix_%s' % fixer for fixer in fixers)
            print('Running 2to3 on %d files, this may take a while ...' % len(files))
            distutils_build_py.run_2to3(self, files)
