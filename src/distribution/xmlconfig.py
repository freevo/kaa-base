# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# xmlconfig.py - xml config to python converter
# -----------------------------------------------------------------------------
# $Id$
#
# -----------------------------------------------------------------------------
# Copyright (C) 2006 Dirk Meyer, Jason Tackaberry
#
# First Edition: Dirk Meyer <dmeyer@tzi.de>
# Maintainer:    Dirk Meyer <dmeyer@tzi.de>
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

__all__ = [ 'convert' ]

# python imports
import sys
import pprint


def get_value(value, type):
    if value is None:
        return eval('%s()' % type)
    if type is not None:
        return eval(type)(value)
    if value.lower() == 'true':
        return True
    if value.lower() == 'false':
        return False
    if value.isdigit():
        return int(value)
    return str(value)


def format_content(node):
    s = node.get_rawcontent().replace('\t', '        ')
    spaces = ''
    while s:
        if s[0] == ' ':
            spaces += ' '
            s = s[1:]
            continue
        if s[0] == '\n':
            spaces = ''
            s = s[1:]
            continue
        break
    return s.replace('\n' + spaces, '\n').strip()


class Parser(object):

    def _get_schema(self, node):
        schema = []
        for child in node:
            if hasattr(self, '_parse_%s' % child.name):
                schema.append(child)
        return schema

    
    def parse(self, node, fd, deep=''):
        fd.write('%s(' % node.name.capitalize())
        first = True
        if node.getattr('name'):
            fd.write('name=\'%s\'' % node.getattr('name'))
            first = False
        for child in node:
            if child.name != 'desc':
                continue
            if not first:
                fd.write(', ')
            first = False
            desc = format_content(child)
            if desc.find('\n') > 0:
                desc = deep + desc.replace('\n', '\n' + deep)
                fd.write('desc=\'\'\'\n%s\n%s\'\'\'' % (desc, deep))
            else:
                fd.write('desc=\'%s\'' % desc)
        getattr(self, '_parse_%s' % node.name.lower())(node, fd, deep, first)
    

    def _parse_var(self, node, fd, deep, first):
        default = node.getattr('default')
        deftype = node.getattr('type')
        if default or deftype:
            if not first:
                fd.write(', ')
            first = False
            default = get_value(default, deftype)
            fd.write('default=%s' % pprint.pformat(default).strip())

        for child in node:
            if child.name not in ('values'):
                continue
            if not first:
                fd.write(', ')
            first = False
            values = []
            for value in child.children:
                values.append(get_value(value.content, value.getattr('type')))
            fd.write('type=%s' % pprint.pformat(tuple(values)).strip())
            break
        fd.write(')')

    
    def _parse_config(self, node, fd, deep, first):
        self._parse_group(node, fd, deep, first)
        

    def _parse_group(self, node, fd, deep, first):
        if not first:
            fd.write(', ')
        deep = deep + '  '
        fd.write('schema=[\n\n' + deep)
        for s in self._get_schema(node):
            self.parse(s, fd, deep)
            fd.write(',\n\n' + deep)
        deep = deep[:-2]
        fd.write(']\n' + deep)
        fd.write(')')
    
    
    def _parse_list(self, node, fd, deep, first):
        if not first:
            fd.write(', ')
        schema = self._get_schema(node)
        fd.write('schema=')
        if len(schema) > 1:
            deep = deep + '  '
            fd.write('[\n\n' + deep)
        for s in schema:
            self.parse(s, fd, deep)
            if len(schema) > 1:
                fd.write(',\n\n' + deep)
        if len(schema) > 1:
            deep = deep[:-2]
            fd.write(']\n' + deep)
        fd.write(')')


    def _parse_dict(self, node, fd, deep, first):
        self._parse_list(node, fd, deep, first)
        


def convert(xml, python):
    # import here and not before or kaa.base install itself
    # will fail because there is no kaa.base at that time.
    import kaa.xml

    tree = kaa.xml.Document(xml, 'config')
    # out = sys.__stdout__
    out = open(python, 'w')
    
    out.write('# auto generated file\n\n')
    out.write('from kaa.config import Var, Group, Dict, List, Config\n\n')
    out.write('config = ')

    Parser().parse(tree, out)
    out.write('\n\n')
    for child in tree:
        if child.name != 'code':
            continue
        out.write(format_content(child) + '\n\n')
